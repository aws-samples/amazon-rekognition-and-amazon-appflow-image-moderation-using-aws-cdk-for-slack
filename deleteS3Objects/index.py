import boto3
import os


def on_event(event, context):
  print(event)
  request_type = event['RequestType']
  if request_type == 'Create': return on_create(event)
  if request_type == 'Update': return on_update(event)
  if request_type == 'Delete': return on_delete(event)
  raise Exception("Invalid request type: %s" % request_type)

def on_create(event):
  print("Nothing to do on Create")


def on_update(event):
  print("Nothing to do on Update")

def on_delete(event):
    bucket = boto3.resource('s3').Bucket(os.environ["BucketName"])
    bucket.objects.all().delete()