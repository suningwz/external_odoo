# -*- coding: utf-8 -*-
from odoo import api, fields, models, tools

import logging
_logger = logging.getLogger(__name__)

import json

import boto3
from botocore.exceptions import ClientError

class ExternalStockPicking(models.Model):
    _inherit = 'external.stock.picking'        
    
    @api.one
    def action_run(self):
        return_item = super(ExternalStockPicking, self).action_run()        
        return return_item
    
    @api.model
    def cron_external_stock_picking_update_shipping_expedition_woocommerce(self):
        _logger.info('cron_external_stock_picking_update_shipping_expedition_woocommerce')        
        #search
        external_source_ids = self.env['external.source'].sudo().search([('type', '=', 'woocommerce'),('api_status', '=', 'valid')])
        if len(external_source_ids)>0:
            for external_source_id in external_source_ids:
                #external_stock_picking_ids
                external_stock_picking_ids = self.env['external.stock.picking'].sudo().search(
                    [   
                        ('external_source_id', '=', external_source_id.id),
                        ('woocommerce_state', 'in', ('processing', 'shipped')),
                        ('picking_id', '!=', False),
                        ('picking_id.state', '=', 'done'),
                        ('picking_id.shipping_expedition_id', '!=', False),
                        ('picking_id.shipping_expedition_id.state', '=', 'delivered')
                    ]
                )
                if len(external_stock_picking_ids)>0:
                    #wcapi (init)
                    wcapi = external_source_id.init_api_woocommerce()[0]            
                    #operations
                    for external_stock_picking_id in external_stock_picking_ids:
                        #put
                        data = {"status": "completed"}                
                        response = wcapi.put("orders/"+str(external_stock_picking_id.number), data).json()
                        if 'id' in response:
                            #update OK
                            external_stock_picking_id.woocommerce_state = 'completed'
    
    @api.model
    def cron_sqs_external_stock_picking_woocommerce(self):
        _logger.info('cron_sqs_external_stock_picking_woocommerce')

        sqs_url = tools.config.get('sqs_external_stock_picking_woocommerce_url')
        AWS_ACCESS_KEY_ID = tools.config.get('aws_access_key_id')
        AWS_SECRET_ACCESS_KEY = tools.config.get('aws_secret_key_id')
        AWS_SMS_REGION_NAME = tools.config.get('aws_region_name')
        # boto3
        sqs = boto3.client(
            'sqs',
            region_name=AWS_SMS_REGION_NAME,
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY
        )
        # Receive message from SQS queue
        total_messages = 10
        while total_messages > 0:
            response = sqs.receive_message(
                QueueUrl=sqs_url,
                AttributeNames=['All'],
                MaxNumberOfMessages=10,
                MessageAttributeNames=['All']
            )
            if 'Messages' in response:
                total_messages = len(response['Messages'])
            else:
                total_messages = 0
            # continue
            if 'Messages' in response:
                for message in response['Messages']:
                    # message_body
                    message_body = json.loads(message['Body'])
                    # fix message
                    if 'Message' in message_body:
                        message_body = json.loads(message_body['Message'])
                    #message_body
                    _logger.info(message_body)
                    # result_message
                    result_message = {
                        'statusCode': 200,
                        'return_body': 'OK',
                        'delete_message': False,
                        'message': message_body
                    }
                    #line_items
                    if 'line_items' not in message_body:
                        result_message['statusCode'] = 500
                        result_message['delete_message'] = True
                        result_message['return_body'] = {'error': 'Falta el campo line_items'}
                    #default
                    source = 'woocommerce'
                    # fields_need_check
                    fields_need_check = ['status', 'shipping', 'billing', 'X-WC-Webhook-Source']
                    for field_need_check in fields_need_check:
                        if field_need_check not in message_body:
                            result_message['statusCode'] = 500
                            result_message['delete_message'] = True
                            result_message['return_body'] = 'No existe el campo ' + str(field_need_check)
                    # operations_1
                    if result_message['statusCode'] == 200:
                        #source_url
                        source_url = str(message_body['X-WC-Webhook-Source'])
                        #external_source_id
                        external_source_ids = self.env['external.source'].sudo().search([('type', '=', str(source)),('url', '=', str(source_url))])
                        if len(external_source_ids)==0:
                            result_message['statusCode'] = 500
                            result_message['return_body'] = {'error': 'No existe external_source id con este source='+str(source)+' y url='+str(source_url)}
                        else:
                            external_source_id = external_source_ids[0]                        
                        #status
                        if message_body['status'] not in ['processing', 'completed', 'shipped', 'refunded']:
                            result_message['statusCode'] = 500
                            result_message['delete_message'] = True
                            result_message['return_body'] = {'error': 'El pedido no esta completado'}
                        # create-write
                        if result_message['statusCode'] == 200:  # error, data not exists
                            #operaciones varias para crearlos
                            #external_customer                                  
                            external_customer_vals = {
                                'external_source_id': external_source_id.id,
                                'active': True,
                                'external_id': int(message_body['customer_id']),
                                'province_code': str(message_body['shipping']['state']),
                                'country_code': str(message_body['shipping']['country'])                                        
                            }
                            #vat
                            if 'meta_data' in message_body:
                                for meta_data_item in message_body['meta_data']:
                                    if meta_data_item['key']=='NIF':
                                        external_customer_vals['vat'] = str(meta_data_item['value'])                                                            
                            #fields_billing
                            fields_billing = ['email', 'phone']
                            for field_billing in fields_billing:
                                if field_billing in message_body['billing']:
                                    if message_body['billing'][field_billing]!='':
                                        external_customer_vals[field_billing] = str(message_body['billing'][field_billing])                                        
                            #fields_shipping
                            fields_shipping = ['first_name', 'last_name', 'company', 'address_1', 'address_2', 'city', 'postcode']
                            for field_shipping in fields_shipping:
                                if field_shipping in message_body['shipping']:
                                    if message_body['shipping'][field_shipping]!='':
                                        external_customer_vals[field_shipping] = str(message_body['shipping'][field_shipping])
                            #fix external_id=0
                            if external_customer_vals['external_id']==0:
                                if 'email' in external_customer_vals:
                                    external_customer_vals['external_id'] = str(external_customer_vals['email'])                                                                    
                            #search_previous
                            external_customer_ids = self.env['external.customer'].sudo().search(
                                [
                                    ('external_source_id', '=', external_source_id.id),
                                    ('external_id', '=', str(external_customer_vals['external_id']))                                    
                                ]
                            )                                                        
                            if len(external_customer_ids)>0:
                                external_customer_obj = external_customer_ids[0]
                            else:
                                #create
                                external_customer_obj = self.env['external.customer'].sudo(6).create(external_customer_vals) 
                            #external_stock_picking                                
                            external_stock_picking_vals = {
                                'external_id': str(message_body['id']),
                                'external_customer_id': external_customer_obj.id,
                                'external_source_id': external_source_id.id,
                                'woocommerce_state': str(message_body['status']),
                                'number': str(message_body['number']),
                                'external_source_name': 'web'    
                            }
                            #search_previous
                            external_stock_picking_ids = self.env['external.stock.picking'].sudo().search(
                                [
                                    ('external_id', '=', str(external_stock_picking_vals['external_id'])),
                                    ('external_source_id', '=', external_source_id.id)
                                ]
                            )
                            if len(external_stock_picking_ids)>0:
                                external_stock_picking_id = external_stock_picking_ids[0]
                                external_stock_picking_id.woocommerce_state = str(message_body['status'])
                                #action_run (only if need)
                                external_stock_picking_id.action_run()
                                #result_message
                                result_message['delete_message'] = True
                                result_message['return_body'] = {'message': 'Como ya existe, actualizamos el estado del mismo unicamente'}
                            else:                                
                                external_stock_picking_obj = self.env['external.stock.picking'].sudo(6).create(external_stock_picking_vals)
                                #lines
                                for line_item in message_body['line_items']:
                                    #vals
                                    external_stock_picking_line_vals = {
                                        'line_id': str(line_item['id']),
                                        'external_id': str(line_item['product_id']),
                                        'external_variant_id': str(line_item['variation_id']),                                        
                                        'external_stock_picking_id': external_stock_picking_obj.id,
                                        'title': str(line_item['name']),
                                        'quantity': int(line_item['quantity'])    
                                    }
                                    external_stock_picking_line_obj = self.env['external.stock.picking.line'].sudo(6).create(external_stock_picking_line_vals)
                                #action_run
                                external_stock_picking_obj.action_run()
                                #delete_message
                                result_message['delete_message'] = True
                    #logger
                    _logger.info(result_message)                                                            
                    # remove_message
                    if result_message['delete_message']==True:
                        response_delete_message = sqs.delete_message(
                            QueueUrl=sqs_url,
                            ReceiptHandle=message['ReceiptHandle']
                        )