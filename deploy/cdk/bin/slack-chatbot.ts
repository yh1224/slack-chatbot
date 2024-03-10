#!/usr/bin/env node
import "source-map-support/register";
import * as cdk from "aws-cdk-lib";
import {SlackChatbotStack} from "../lib/slack-chatbot-stack";
import {createConfig} from "../lib/config";

const app = new cdk.App();
const config = createConfig(app.node.tryGetContext("env") || process.env.ENV);

new SlackChatbotStack(app, "SlackChatbotStack", {
    env: config.env,
    stackName: config.stackName,
    config,
});
