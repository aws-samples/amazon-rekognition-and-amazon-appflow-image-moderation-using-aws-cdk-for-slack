import urllib.request
import boto3
import os

sqs = boto3.client('sqs')
rekognition = boto3.client('rekognition')


def analyze_themes(file, min_confidence=80):
    with open(file, 'rb') as document:
        imageBytes = bytearray(document.read())

    response = rekognition.detect_moderation_labels(Image={'Bytes': imageBytes}, MinConfidence=min_confidence)

    found_high_confidence_labels = []
    for label in response['ModerationLabels']:
        found_high_confidence_labels.append(str(label['Name']))

    return found_high_confidence_labels


def analyze_text(file):
    with open(file, 'rb') as document:
        imageBytes = bytearray(document.read())

    response = rekognition.detect_text(Image={'Bytes': imageBytes})

    textDetections = response['TextDetections']

    found_text = ""
    for text in textDetections:
        found_text += text['DetectedText']

    return found_text


def sendToSqS(words, attributes, queueurl):

    sqs.send_message(
        QueueUrl=queueurl,
        MessageBody='Image with "' + words + '" found',
        MessageAttributes={
            "url": {
                "StringValue": attributes["image_url"],
                "DataType": 'String'
            },
            "slack_msg_id": {
                "StringValue": attributes["slack_msg_id"],
                "DataType": 'String'
            }
        }
    )


def lambda_handler(event, context):

    violations_queue = os.environ["SQS_QUEUE_URL"]

    disallowed_words = ["private", "security"]

    # Categories listed here - https://docs.aws.amazon.com/rekognition/latest/dg/moderation.html#moderation-api
    disallowed_themes = ["Tobacco", "Alcohol"]  # Case Sensitive

    file_name = "/tmp/image.jpg"

    for record in event['Records']:
        print(record)
        receiptHandle = record["receiptHandle"]
        image_url = record["messageAttributes"]["url"]["stringValue"]
        slack_msg_id = record["messageAttributes"]["slack_msg_id"]["stringValue"]
        eventSourceARN = record["eventSourceARN"]

        arn_elements = eventSourceARN.split(':')

        img_queue_url = sqs.get_queue_url(
            QueueName=arn_elements[5],
            QueueOwnerAWSAccountId=arn_elements[4]
        )

        sqs.delete_message(
            QueueUrl=img_queue_url["QueueUrl"],
            ReceiptHandle=receiptHandle
        )

        urllib.request.urlretrieve(image_url, file_name)

        detected_text = analyze_text(file_name)

        print("Detected Text: " + detected_text)

        found_words = []
        for disallowed_word in disallowed_words:
            if disallowed_word.lower() in detected_text.lower():
                found_words.append(disallowed_word)
                print("WORD VIOLATION: " + disallowed_word.lower() + " found in " + detected_text.lower())

        violating_words = ", ".join(found_words)
        if not violating_words == "":
            attributes_json = {}
            attributes_json["slack_msg_id"] = slack_msg_id
            attributes_json["image_url"] = image_url
            sendToSqS(violating_words, attributes_json, violations_queue)

        detected_themes = analyze_themes(file_name)

        print("Detected Themes: " + ", ".join(detected_themes))

        found_themes = []
        for disallowed_theme in disallowed_themes:
            if disallowed_theme in detected_themes:
                found_themes.append(disallowed_theme)
                print("THEME VIOLATION: " + disallowed_theme + " found in image")

        violating_themes = ", ".join(found_themes)
        if not violating_themes == "":
            attributes_json = {}
            attributes_json["slack_msg_id"] = slack_msg_id
            attributes_json["image_url"] = image_url
            sendToSqS(violating_themes, attributes_json, violations_queue)
