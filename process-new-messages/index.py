import boto3
import os
from urllib.parse import unquote_plus
import json

s3_client = boto3.client('s3')
s3 = boto3.resource('s3')
sqs = boto3.client('sqs')


def sendToSqS(attributes, queueurl):

    sqs = boto3.client('sqs')
    sqs.send_message(
        QueueUrl=queueurl,
        MessageBody='Image to Check',
        MessageAttributes={
            "url": {
                "StringValue": attributes["image_url"],
                "DataType": 'String'
            },
            "slack_msg_id": {
                "StringValue": attributes["client_msg_id"],
                "DataType": 'String'
            }
        }
    )


def lambda_handler(event, context):

    image_processing_queueurl = os.environ["SQS_QUEUE_URL"]

    for record in event['Records']:
        bucket = record['s3']['bucket']['name']
        key = unquote_plus(record['s3']['object']['key'])

        file_lines = s3.Object(bucket, key).get()['Body'].read().decode('utf-8').splitlines()

        attachment_list = []

        for line in file_lines:
            if line:  # Check for blank lines
                jsonline = json.loads(line)
                if "attachments" in jsonline.keys():  # Check for lines with attachements
                    for attachment in jsonline["attachments"]:
                        if "image_url" in attachment.keys():
                            if "client_msg_id" in jsonline.keys():
                                thisdict = {
                                    "image_url": attachment["image_url"],
                                    "client_msg_id": jsonline["client_msg_id"]
                                }
                                attachment_list.append(thisdict.copy())
                            else:
                                thisdict = {
                                    "image_url": attachment["image_url"],
                                    "client_msg_id": "None Found"
                                }
                                attachment_list.append(thisdict.copy())

        for item in attachment_list:
            sendToSqS(item, image_processing_queueurl)
