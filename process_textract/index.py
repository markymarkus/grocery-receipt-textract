import os
import json
import boto3
import io
import sys
from datetime import datetime, timedelta
import logging
import re

LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.DEBUG)

OUTPUT_BUCKET = os.environ["OUTPUT_BUCKET"]
IGNORE_PRODUCTS = ["yhteen", "alennus"]
RECEIPT_STORE = ["s-market","prisma","sale","k-market","kcm","k-citymarket"]

textract = boto3.client('textract')

def is_date(date_text):
    date_value = re.search(r'(\d+-\d+-\d+)',date_text)
    if date_value:
        return date_value.group(1)
    else:
        date_value = re.search(r'(\d{1,2}\.\d{1,2}\.\d{4})',date_text)
        if date_value:
            return date_value.group(1).replace(".","-")
        return None

def is_time(time_text):
    hour_min = re.search('(\d{1,2}:\d{2})', time_text)
    if hour_min:
        return hour_min.group(1)
    else:
        return None

def get_rows_columns_map(table_result, blocks_map):
    rows = {}
    for relationship in table_result['Relationships']:
        if relationship['Type'] == 'CHILD':
            for child_id in relationship['Ids']:
                cell = blocks_map[child_id]
                if cell['BlockType'] == 'CELL':
                    row_index = cell['RowIndex']
                    col_index = cell['ColumnIndex']
                    if row_index not in rows:
                        # create new row
                        rows[row_index] = {}
                        
                    # get the text value
                    rows[row_index][col_index] = get_text(cell, blocks_map)
    return rows


def get_text(result, blocks_map):
    text = ''
    if 'Relationships' in result:
        for relationship in result['Relationships']:
            if relationship['Type'] == 'CHILD':
                for child_id in relationship['Ids']:
                    word = blocks_map[child_id]
                    if word['BlockType'] == 'WORD':
                        text += word['Text'] + ' '
                    if word['BlockType'] == 'SELECTION_ELEMENT':
                        if word['SelectionStatus'] =='SELECTED':
                            text +=  'X '    
    return text


def get_table_results(blocks):
    blocks_map = {}
    table_blocks = []

    receipt_store = ""
    for block in blocks:
        blocks_map[block['Id']] = block
        if block['BlockType'] == "TABLE":
            table_blocks.append(block)
        elif block['BlockType'] == "LINE":
            if any(x in block['Text'].lower() for x in RECEIPT_STORE):
                if receipt_store == "":
                    receipt_store = block['Text'].split(",")[0]
            elif is_date(block['Text']):
                receipt_date = is_date(block['Text'])
            
            if is_time(block['Text']):
                receipt_time=is_time(block['Text'])

    if len(table_blocks) <= 0:
        return "<b> NO Table FOUND </b>"

    receipt_products = generate_price_data(table_blocks[0], blocks_map)
    receipt_info = {
        'store': receipt_store,
        'date': receipt_date,
        'time': receipt_time
    }

    return receipt_info, receipt_products

def generate_price_data(table_result, blocks_map):
    rows = get_rows_columns_map(table_result, blocks_map)

    products = []

    for row_index, cols in rows.items():
        is_skipped = False
        product_name = cols[1].strip()
        product_price = ""
        product_unit = ""
        
        for product in IGNORE_PRODUCTS:
            if product in product_name.lower():
                is_skipped = True
                continue
        if not is_skipped and product_name != "":
            if (u"\N{euro sign}" in product_name) or ("EUR/" in product_name):
                tuote_split = product_name.split(" ")

                index = [idx for idx, s in enumerate(tuote_split) if ('EUR/' in s) or (u"\N{euro sign}/" in s)][0]
                product_price = tuote_split[index-1].replace(',','.',1)
                product_name = tuote_split[0]
                product_unit = tuote_split[-1].split("/")[1]
                # Textract splits some receipt rows to two rows, in those cases
                # just update the item price 
                if tuote_split[0].replace('.','',1).isdigit():
                    try:
                        products[-1]['price'] = float(product_price)
                        products[-1]['unit'] = product_unit
                    except:
                        # Textract doesn't always get price right.. If price is not float, delete the item
                        if len(products) > 0:
                            del products[-1]
                    continue
                else:
                    # product name, product price and total are on the same row
                    name_length = len(tuote_split)
                    product_name = ' '.join(tuote_split[0:name_length-4])
            else:
                try:
                    product_price = float(cols[2].strip().replace(',','.',1))
                except:
                    LOGGER.error(f"Price is not valid on {product_name} {product_price}")
                    continue

            products.append({
                'name': product_name,
                'price': product_price,
                'unit': product_unit
            })
    
    return products

def lambda_handler(event, context):
    LOGGER.debug(event)
    LOGGER.debug("Record count: "+ str(len(event["Records"])))
    for record in event["Records"]:
        body = json.loads(record["body"])
        message = json.loads(body["Message"])
        job_id = message["JobId"]
        LOGGER.debug("filename: " + str(message["DocumentLocation"]))
        response = textract.get_document_analysis(
            JobId=job_id
        )

        receipt_info, product_data = get_table_results(response['Blocks'])

        datef = datetime.strptime(receipt_info['date'], '%d-%m-%Y')
        hourmin = receipt_info['time'].split(":")
        datef = datef + timedelta(hours=int(hourmin[0]), minutes=int(hourmin[1]))
        
        receipt_file = ""
        for product in product_data:
            item = {
                'name': product['name'],
                'price': product['price'],
                'currency': 'EUR',
                'unit': product['unit'],
                'date': str(datef)
            }
            LOGGER.debug(item)
            # Every json object must be on separate line for Athena
            receipt_file+= json.dumps(item) + "\n"
            
        filename = datef.strftime("%Y%m%d-%H%M%S")+".json"
        prefix = f"store={receipt_info['store']}/"
        LOGGER.debug(prefix+filename)
        # Finally write receipt json object to s3
        s3 = boto3.resource('s3')
        s3object = s3.Object(OUTPUT_BUCKET, prefix+filename)

        s3object.put(
            Body=(bytes(receipt_file.encode('UTF-8')))
        )
