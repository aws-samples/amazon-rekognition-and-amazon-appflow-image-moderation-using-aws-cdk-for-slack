
# Leveraging Amazon Rekognition and Amazon AppFlow for Slack image moderation using AWS Solutions Constructs

# Table of Contents
1. [Overview](#overview)
    1. [About](#about)
    2. [Use Cases](#use-cases)
    3. [Architecture Diagram](#architecture-diagram)
2. [Requirements](#requirements)
    1. [General](#general)
    2. [Slack](#slack-app)
    3. [AWS CDK](#aws-cdk)
    4. [Environment Variable Prep](#environment-variable-prep)
3. [Deployment](#deployment) 
4. [Testing](#testing)
    1. [Trigger Violations](#trigger-violations)
    2. [Checking Results](#checking-results)
5. [Cleanup](#cleanup)

## Overview
The code in this repo automates the solution in the "Moderating Image Content in Slack with Amazon Rekognition and Amazon AppFlow" [Technical Guide](https://docs.aws.amazon.com/whitepapers/latest/moderating-image-content-in-slack/moderating-image-content-in-slack.html)

### About 
This project deploys a fully serverless pipeline to moderate images posted to a [Slack](https://slack.com/) channel using the [AWS CDK](https://aws.amazon.com/cdk/) along with [AWS Solutions Constructs](https://aws.amazon.com/solutions/constructs/). Services used are: [Amazon Rekognition](https://aws.amazon.com/rekognition/), [Amazon AppFlow](https://aws.amazon.com/appflow/), [AWS Lambda](https://aws.amazon.com/lambda/),[Amazon S3](https://aws.amazon.com/s3/) and [Amazon SQS](https://aws.amazon.com/sqs/)

### Use Cases
Ensuring all aspects of the virtual work environment are inclusive and safe is a priority for many organizations. Sharing images can be a powerful way to effectively convey concepts and thoughts. There are many popular ways to analyze text, but images present a different challenge. Organizations need a way to detect and react to posted images that violate company guidelines.

The content moderation strategy in this solution identifies images that violate sample chosen guidelines:

Images that contain themes of tobacco or alcohol using Amazon Rekognition [content moderation](https://docs.aws.amazon.com/rekognition/latest/dg/moderation.html).

Images that contain the following disallowed words using using Amazon Rekognition [text detection](https://docs.aws.amazon.com/rekognition/latest/dg/text-detection.html):
* security
* private

These guidelines can be customized in the [process-new-images/index.py](process-new-images/index.py) file to fit your requirements.

### Architecture Diagram 
![Architecture Diagram](images/arch-diagram.png?raw=true)

## Requirements 

### General 
* A Linux or MacOS-compatible machine
* An [AWS account](https://aws.amazon.com/premiumsupport/knowledge-center/create-and-activate-aws-account/) with sufficient permissions
* AWS CLI [installed](https://docs.aws.amazon.com/cli/latest/userguide/cli-chap-install.html)
* A [Slack workspace](https://slack.com/help/articles/206845317-Create-a-Slack-workspace) that you have permissions to create an App in

### Slack app
Create a [Slack app](https://api.slack.com/start) and install the Slack app into your Slack workspace 
Follow the steps in the "Creating the Slack app in your Slack workspace" section of the Moderating Image Content in Slack with Amazon Rekognition and Amazon AppFlow [Technical Guide](https://docs.aws.amazon.com/whitepapers/latest/moderating-image-content-in-slack/creating-the-slack-app-in-your-slack-workspace.html)

In your Slack Workspace, create a channel called 'testing-slack-moderation' (or something else you prefer)

### AWS CDK
Install the AWS CDK - [Getting Started Guide](https://docs.aws.amazon.com/cdk/latest/guide/getting_started.html)

### Environment Variable Prep
Export the following environment variables in your terminal session. These are used by the CDK to configure the solution during deployment. 

* SlackClientID (Obtained from the steps above when creating your Slack app)
* SlackClientSecret (Obtained from the steps above when creating your Slack app)
* SlackWorkspaceInstanceURL (Based on your Slack workspace name)
* SlackChannelParamID (Obtained by navigating to your Slack workspace and channel in the [web interface of Slack](https://app.slack.com/). It is the last portion of the URL (following the last forward slash) )
![Channel ID](/images/channel-id.png)
* SlackOAuthAccessToken (Obtained from your [Slack app's management page](https://api.slack.com/apps). Under the Features menu select the OAuth & Permissions option. Be sure to use the "User OAuth Token".)


E.g.:
```
export SlackClientID=####...###
export SlackClientSecret=...
export SlackWorkspaceInstanceURL=https://<<WORKSPACENAME>>.slack.com
export SlackChannelParamID=<<ChannelID>>
export SlackOAuthAccessToken=xoxp-...
```

## Deployment
This project is set up like a standard Python AWS CDK project.  

To manually create a virtualenv on MacOS and Linux:

```
$ python3 -m venv .venv
```

After the init process completes and the virtualenv is created, you can use the following
step to activate your virtualenv.

```
$ source .venv/bin/activate
```

Once the virtualenv is activated, you can install the required dependencies.

```
$ pip install -r requirements.txt
```

Deploy the stack 
```
cdk deploy
```

## Testing

### Trigger Violations
Post the following images to the moderated Slack Channel:

This image contains the disallowed word "private": [https://i.imgur.com/uuAY133.png](https://i.imgur.com/uuAY133.png)

This image which contains the disallowed "Tobacco" theme: [https://i.imgur.com/XgAtyWU.png](https://i.imgur.com/662ptww.png)

Note:

If you are pasting the same link numerous times during testing, you may receive a "Pssst! I didn’t unfurl <<URL>> because it was already shared in this channel quite recently ..." error. You will need to click "Show Preview Anyway" for the image to be processed again.

Avoid using images over 2 MB because Slack doesn't expand them by default. 

### Checking results

Wait approximately 2 mins and then check the "new-violation-findings" SQS Queue. 

In the AWS Console, navigate to Amazon SQS --> Queues -->new-violation-findings

![SQS Queue](images/sqsqueue1.png?raw=true)

Click "Send and receive messages" 

Scroll down the the Receive Messages window and click "Poll for messages" 

![SQS Queue](images/sqsqueue2.png?raw=true)

From there, you can select a message and view its details

![SQS Queue](images/sqsqueue3.png?raw=true)

You can get more information by selection the Attributes menu

![SQS Queue](images/sqsqueue4.png?raw=true)

You can also use the following to check violations via the CLI: 

Set your AWS ACCOUNT ID
```
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
```

Set and export your default region to the region of your choice. - Ex:
```
export AWS_REGION=us-east-1
```

Run the following command to retrieve messages: 
```
aws sqs receive-message --queue-url https://sqs.$AWS_REGION.amazonaws.com/$AWS_ACCOUNT_ID/new-violation-findings --attribute-names All --message-attribute-names All --max-number-of-messages 10
```

You should see messages with the following violations: 
```
            <snip>
            "Body": "Image with \"private\" found",
            "Attributes": {
            <snip>
            "MessageAttributes": {
                "slack_msg_id": {
                    "StringValue": "<ID>",
                    "DataType": "String"
                },
                "url": {
                    "StringValue": "https://i.imgur.com/uuAY133.png",
                    "DataType": "String"
                }
            }
```

```
            <snip>
            "Body": "Image with \"Tobacco\" found",
            "Attributes": {
            <snip>
            "MessageAttributes": {
                "slack_msg_id": {
                    "StringValue": "<ID>",
                    "DataType": "String"
                },
                "url": {
                    "StringValue": "https://i.imgur.com/XgAtyWU.png",
                    "DataType": "String"
                }
            }
```

## Clean up
Delete the CDK stack:
```
cdk destroy
```
