import * as cdk from "aws-cdk-lib";
import {Construct} from "constructs";
import * as apigateway from "aws-cdk-lib/aws-apigateway";
import * as certificatemanager from "aws-cdk-lib/aws-certificatemanager";
import * as iam from "aws-cdk-lib/aws-iam";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as lambda_python from "@aws-cdk/aws-lambda-python-alpha";
import * as logs from "aws-cdk-lib/aws-logs";
import {Config} from "./config";

type SlackChatbotStackProps = cdk.StackProps & {
    readonly config: Config;
}

export class SlackChatbotStack extends cdk.Stack {
    constructor(scope: Construct, id: string, props: SlackChatbotStackProps) {
        super(scope, id, props);

        const config = props.config;

        // Lambda Function
        const slackChatbotFunction = new lambda_python.PythonFunction(this, "SlackChatbotFunction", {
            architecture: lambda.Architecture.ARM_64,
            entry: "../../src",
            environment: {
                LOG_LEVEL: config.logLevel || "INFO",
                SLACK_SIGNING_SECRET: config.slackSigningSecret,
                SLACK_BOT_TOKEN: config.slackBotToken,
                SLACK_BOT_MEMBER_ID: config.slackBotMemberId,
                CHATGPT_SETTINGS: JSON.stringify(config.chatGpt),
                BEDROCK_SETTINGS: JSON.stringify(config.bedrock),
            },
            handler: "lambda_handler",
            index: "main.py",
            logRetention: logs.RetentionDays.ONE_WEEK,
            runtime: lambda.Runtime.PYTHON_3_12,
            timeout: cdk.Duration.minutes(1),
        });
        slackChatbotFunction.addToRolePolicy(new iam.PolicyStatement({
            actions: [
                "bedrock:InvokeModel",
                "bedrock:Retrieve",
            ],
            resources: ["*"],
        }));
        // for Lazy listener
        const invokeFunctionPolicy = new iam.Policy(this, "InvokeFunctionPolicy", {
            statements: [
                new iam.PolicyStatement({
                    actions: ["lambda:InvokeFunction"],
                    resources: [slackChatbotFunction.functionArn],
                }),
            ],
        });
        invokeFunctionPolicy.attachToRole(slackChatbotFunction.role!);

        if (config.domainName && config.certificateArn) {
            // use API Gateway
            const api = new apigateway.LambdaRestApi(this, "Api", {
                restApiName: "slack-chatbot-api",
                handler: slackChatbotFunction,
            });
            const apiGatewayDomainName = new apigateway.DomainName(this, "ApiGatewayDomainName", {
                certificate: certificatemanager.Certificate.fromCertificateArn(this, "Certificate", config.certificateArn),
                domainName: config.domainName,
            });
            apiGatewayDomainName.addBasePathMapping(api, {});
        } else {
            // use Lambda Function URL
            const apiUrl = slackChatbotFunction.addFunctionUrl({
                authType: lambda.FunctionUrlAuthType.NONE,
            });
            new cdk.CfnOutput(this, "ApiUrl", {
                value: apiUrl.url,
            });
        }
    }
}
