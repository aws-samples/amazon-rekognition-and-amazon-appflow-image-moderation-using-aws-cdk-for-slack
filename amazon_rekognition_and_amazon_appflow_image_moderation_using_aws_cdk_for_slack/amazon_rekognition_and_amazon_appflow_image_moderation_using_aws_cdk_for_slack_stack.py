
import os
import boto3

from aws_cdk import (
    aws_lambda,
    aws_s3,
    aws_sqs,
    aws_iam,
    cloudformation_include as cfn_inc,
    aws_appflow,
    custom_resources,
    aws_logs as logs,
    core as cdk,
)

from aws_solutions_constructs import (
    aws_s3_lambda as s3_to_lambda,
    aws_lambda_sqs_lambda as lambda_sqs_lambda,
    aws_lambda_sqs as lambda_sqs
)


class AmazonRekognitionAndAmazonAppflowImageModerationUsingAwsCdkForSlackStack(cdk.Stack):

    def __init__(self, scope: cdk.Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        S3ToLambda = s3_to_lambda.S3ToLambda(
            self,
            'S3ToLambda',
            lambda_function_props=aws_lambda.FunctionProps(
                code=aws_lambda.AssetCode("./process-new-messages"),
                handler="index.lambda_handler",
                runtime=aws_lambda.Runtime.PYTHON_3_8,
                description="cdk-process-new-messages",
                timeout=cdk.Duration.seconds(30),
            ),
            bucket_props=aws_s3.BucketProps(
                removal_policy=cdk.RemovalPolicy.DESTROY, # Set for easy teardown during testing, change for Production usage
                auto_delete_objects=True # Set for easy teardown during testing, change for Production usage
            )
        )

        S3ToLambda.s3_bucket.add_to_resource_policy(
            aws_iam.PolicyStatement(
            effect=aws_iam.Effect.ALLOW,
            actions=[
                "s3:PutObject",
                "s3:AbortMultipartUpload",
                "s3:ListMultipartUploadParts",
                "s3:ListBucketMultipartUploads",
                "s3:GetBucketAcl",
                "s3:PutBucketAcl"],
            resources=[
                S3ToLambda.s3_bucket.bucket_arn,
                S3ToLambda.s3_bucket.bucket_arn + "/*"],
            principals=[aws_iam.ServicePrincipal('appflow.amazonaws.com')]
            )
        )

        # Grant the Lambda Function read access to the S3 Bucket for file processing
        S3ToLambda.s3_bucket.grant_read(S3ToLambda.lambda_function)

        LambdaToSqsToLambdaPattern = lambda_sqs_lambda.LambdaToSqsToLambda(
            self,
            'LambdaToSqsToLambdaPattern',
            existing_producer_lambda_obj=S3ToLambda.lambda_function,
            consumer_lambda_function_props=aws_lambda.FunctionProps(
                code=aws_lambda.AssetCode("./process-new-images"),
                handler="index.lambda_handler",
                runtime=aws_lambda.Runtime.PYTHON_3_8,
                description="cdk-process-new-images",
                timeout=cdk.Duration.seconds(30)
            ),
            queue_props=aws_sqs.QueueProps(
                queue_name="new-image-findings"
            )
        )

        # Grant the Lambda Function access to Rekognition by adding the managed policy to the execution role
        LambdaToSqsToLambdaPattern.consumer_lambda_function.add_to_role_policy(aws_iam.PolicyStatement(
            effect=aws_iam.Effect.ALLOW,
            resources=["*"], # There aren't any Rekognition resource that we can use for the Detect* Actions https://docs.aws.amazon.com/service-authorization/latest/reference/list_amazonrekognition.html#amazonrekognition-resources-for-iam-policies
            actions=["rekognition:Detect*"])
        )

        lambda_sqs.LambdaToSqs(
            self,
            'LambdaToSqsPattern',
            existing_lambda_obj=LambdaToSqsToLambdaPattern.consumer_lambda_function,
            queue_props=aws_sqs.QueueProps(
                queue_name="new-violation-findings"
            )
        )

        #Note from: https://docs.aws.amazon.com/appflow/latest/userguide/slack.html#slack-setup
        #Set the redirect URL (RedirectLocation below) as follows:
        #https://console.aws.amazon.com/appflow/oauth for the us-east-1 Region
        #https://region.console.aws.amazon.com/appflow/oauth for all other Regions
        if cdk.Aws.REGION == "us-east-1":
            RedirectLocation="https://console.aws.amazon.com/appflow/oauth"
        else:
            RedirectLocation="https://" + cdk.Aws.REGION +".console.aws.amazon.com/appflow/oauth"

        ConnectorProfileConfig = aws_appflow.CfnConnectorProfile.ConnectorProfileConfigProperty(
            connector_profile_credentials = aws_appflow.CfnConnectorProfile.ConnectorProfileCredentialsProperty(
                slack = aws_appflow.CfnConnectorProfile.SlackConnectorProfileCredentialsProperty(
                    access_token=os.environ["SlackOAuthAccessToken"],
                    client_id=os.environ["SlackClientID"],
                    client_secret=os.environ["SlackClientSecret"],
                    connector_o_auth_request = aws_appflow.CfnConnectorProfile.ConnectorOAuthRequestProperty(
                        redirect_uri=RedirectLocation
                    )
                )
            ),
            connector_profile_properties = aws_appflow.CfnConnectorProfile.ConnectorProfilePropertiesProperty(
                slack = aws_appflow.CfnConnectorProfile.SlackConnectorProfilePropertiesProperty(
                    instance_url=os.environ["SlackWorkspaceInstanceURL"]
                )
            )
        )

        appFlowConnector = aws_appflow.CfnConnectorProfile(
            self,
            'appFlowConnector',
            connection_mode="Public",
            connector_profile_name="SlackAppFlowModeration",
            connector_type="Slack",
            connector_profile_config=ConnectorProfileConfig
        )

        S3ToLambda.s3_bucket.add_to_resource_policy(aws_iam.PolicyStatement(
            effect=aws_iam.Effect.ALLOW,
            actions=["s3:putobjectacl"],
            resources=[S3ToLambda.s3_bucket.bucket_arn,S3ToLambda.s3_bucket.bucket_arn+"/*"],
            principals=[aws_iam.ServicePrincipal('appflow.amazonaws.com')]
            )
        )

        DestinationFlowConfigList = [aws_appflow.CfnFlow.DestinationFlowConfigProperty(
            connector_profile_name = appFlowConnector.connector_profile_name,
            connector_type="S3",
            destination_connector_properties = aws_appflow.CfnFlow.DestinationConnectorPropertiesProperty(
                s3 = aws_appflow.CfnFlow.S3DestinationPropertiesProperty(
                    bucket_name=S3ToLambda.s3_bucket.bucket_name
                )
            )
        )]

        SourceFlowConfig = aws_appflow.CfnFlow.SourceFlowConfigProperty(
            connector_profile_name = appFlowConnector.connector_profile_name,
            connector_type="Slack",
            source_connector_properties = aws_appflow.CfnFlow.SourceConnectorPropertiesProperty(
                slack = aws_appflow.CfnFlow.SlackSourcePropertiesProperty(
                    object="conversations/"+ os.environ["SlackChannelParamID"]
                )
            )
        )

        TriggerConfig = aws_appflow.CfnFlow.TriggerConfigProperty(
            trigger_type="Scheduled",
            trigger_properties = aws_appflow.CfnFlow.ScheduledTriggerPropertiesProperty(
                data_pull_mode="Incremental",
                schedule_expression="rate(1 minute)"
            )
        )

        appFlow = aws_appflow.CfnFlow(
            self,
            'AppFlowflow',
            destination_flow_config_list=DestinationFlowConfigList,
            flow_name="SlackAppFlow",
            source_flow_config=SourceFlowConfig,
            trigger_config=TriggerConfig,
            tasks=[
                aws_appflow.CfnFlow.TaskProperty(
                    source_fields=["text","attachments","client_msg_id"],
                    task_type="Filter",
                    connector_operator=aws_appflow.CfnFlow.ConnectorOperatorProperty(slack="PROJECTION")
                ),
                aws_appflow.CfnFlow.TaskProperty(
                    source_fields=["text"],
                    task_type="Map",
                    connector_operator=aws_appflow.CfnFlow.ConnectorOperatorProperty(slack="NO_OP"),
                    destination_field="text",
                    task_properties=[
                        aws_appflow.CfnFlow.TaskPropertiesObjectProperty(
                            key="DESTINATION_DATA_TYPE",
                            value="string"
                        ),
                        aws_appflow.CfnFlow.TaskPropertiesObjectProperty(
                            key="SOURCE_DATA_TYPE",
                            value="string"
                        )
                    ]
                ),
                aws_appflow.CfnFlow.TaskProperty(
                    source_fields=["attachments"],
                    task_type="Map",
                    connector_operator=aws_appflow.CfnFlow.ConnectorOperatorProperty(slack="NO_OP"),
                    destination_field="attachments",
                    task_properties=[
                        aws_appflow.CfnFlow.TaskPropertiesObjectProperty(
                            key="DESTINATION_DATA_TYPE",
                            value="string"
                        ),
                        aws_appflow.CfnFlow.TaskPropertiesObjectProperty(
                            key="SOURCE_DATA_TYPE",
                            value="string"
                        )
                    ]
                ),
                aws_appflow.CfnFlow.TaskProperty(
                    source_fields=["client_msg_id"],
                    task_type="Map",
                    connector_operator=aws_appflow.CfnFlow.ConnectorOperatorProperty(slack="NO_OP"),
                    destination_field="client_msg_id",
                    task_properties=[
                        aws_appflow.CfnFlow.TaskPropertiesObjectProperty(
                            key="DESTINATION_DATA_TYPE",
                            value="string"
                        ),
                        aws_appflow.CfnFlow.TaskPropertiesObjectProperty(
                            key="SOURCE_DATA_TYPE",
                            value="string"
                        )
                    ]
                )
            ]
        )

        # Activate the AppFlow flow when it is created
        # Set for easy teardown during testing, change for Production usage
        appflow_on_create = custom_resources.AwsSdkCall(
            action='startFlow',
            service='Appflow',
            parameters={
                "flowName": appFlow.flow_name,
            },
            physical_resource_id=custom_resources.PhysicalResourceId.of('AppFlowflow')
        )

        # Deactivate the AppFlow flow before it can be deleted 
        appflow_on_delete = custom_resources.AwsSdkCall(
            action='stopFlow',
            service='Appflow',
            parameters={
                "flowName": appFlow.flow_name,
            },
            physical_resource_id=custom_resources.PhysicalResourceId.of('AppFlowflow')
        )

        appflow_policy_statement = aws_iam.PolicyStatement(
            actions=["appflow:StartFlow","appflow:StopFlow"],
            effect=aws_iam.Effect.ALLOW,
            resources=["arn:" + cdk.Aws.PARTITION + ":appflow:" + cdk.Aws.REGION + ":" + cdk.Aws.ACCOUNT_ID + ":flow/" + appFlow.flow_name],
        )

        appflow_policy = custom_resources.AwsCustomResourcePolicy.from_statements(
            statements=[appflow_policy_statement]
        )

        custom_resources.AwsCustomResource(
            self,
            'AppFlowCustomResource',
            policy=appflow_policy,
            on_create=appflow_on_create,
            on_delete=appflow_on_delete,
            log_retention=logs.RetentionDays.TWO_WEEKS
        )

        # Delete the files in the logging bucket before removal 
        # Currently this is not possible with the CDK Solutions Contruct being used 
        # https://github.com/awslabs/aws-solutions-constructs/issues/213
        # Set for easy teardown during testing, change for Production usage

        s3log_handler=aws_lambda.Function(
            self, 
            'S3DeleteLambdaFunction',
            code=aws_lambda.AssetCode("./deleteS3Objects"),
            handler="index.on_event",
            runtime=aws_lambda.Runtime.PYTHON_3_8,
            timeout=cdk.Duration.seconds(30),
            environment={
                "BucketName": S3ToLambda.s3_logging_bucket.bucket_name,
            }
        )

        s3log_policy_statement = aws_iam.PolicyStatement(
            actions=["s3:Get*","s3:List*","s3:Delete*"],
            effect=aws_iam.Effect.ALLOW,
            resources=[S3ToLambda.s3_logging_bucket.bucket_arn],
        )

        iam_role = aws_iam.Role(self, "S3DeleteLambda", assumed_by=aws_iam.ServicePrincipal("lambda.amazonaws.com"))

        iam_role.add_to_policy(s3log_policy_statement)

        custom_resources.Provider(
            self,
            'S3CustomResource',
            on_event_handler=s3log_handler,
            log_retention=logs.RetentionDays.TWO_WEEKS,
            role=iam_role
        )
