import boto3
import os
import logging

LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.DEBUG)

client = boto3.client('textract')

def lambda_handler(event, context):
    LOGGER.debug(event)
    bucket_name = event["detail"]["bucket"]["name"]
    key = event["detail"]["object"]["key"]
    document_location={
        'S3Object': {
            'Bucket': bucket_name,
            'Name': key
        }
    }
    response = client.start_document_analysis(
        DocumentLocation=document_location,
        FeatureTypes=['TABLES'],
        NotificationChannel={
            'SNSTopicArn': os.environ["DOCUMENT_ANALYIS_COMPLETED_SNS_TOPIC_ARN"],
            'RoleArn': os.environ["TEXTRACT_PUBLISH_TO_SNS_ROLE_ARN"]
        }
    )
    event["job_id"]=response["JobId"] 
    LOGGER.debug(response["JobId"])
    return event