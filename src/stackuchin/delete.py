import boto3
import botocore
import yaml
from datetime import datetime

from stackuchin.utilities import alert

import warnings

warnings.filterwarnings("ignore")


def delete(profile_name, stack_file, stack_name, slack_webhook_url, from_pipeline=False):
    aws_region = None
    aws_account = None
    stacks = None
    stack_template = None
    action = 'DELETE'
    client_token = datetime.utcnow().isoformat().replace(":", "-").replace(".", "-")

    stacks = None
    try:
        with open(stack_file, 'r') as stack_stream:
            stacks = yaml.safe_load(stack_stream)
    except yaml.YAMLError as exc:
        print(exc)
        exit(1)

    if stack_name not in stacks:
        print("{} was not found in your stack file.".format(stack_name))
        if from_pipeline:
            alert(stack_name,
                  "{} was not found in your stack file {}.".format(
                      stack_name, stack_file),
                  None, None, action, profile_name, slack_webhook_url)
        exit(1)

    if 'Account' not in stacks[stack_name]:
        print("The Account property is missing from the stack definition.")
        if from_pipeline:
            alert(stack_name,
                  "The Account property is missing from the stack {} in stack_file {}.".format(
                      stack_name, stack_file),
                  None, None, action, profile_name, slack_webhook_url)
        exit(1)

    if 'Region' not in stacks[stack_name]:
        print("The Region property is missing from the stack definition.")
        if from_pipeline:
            alert(stack_name,
                  "The Region property is missing from the stack {} in stack_file {}.".format(
                      stack_name, stack_file),
                  None, None, action, profile_name, slack_webhook_url)
        exit(1)

    if 'Template' not in stacks[stack_name]:
        print("The Template property is missing from the stack definition.")
        if from_pipeline:
            alert(stack_name,
                  "The Template property is missing from the stack {} in stack_file {}.".format(
                      stack_name, stack_file),
                  None, None, action, profile_name, slack_webhook_url)
        exit(1)

    if 'Parameters' not in stacks[stack_name]:
        print("The Parameters property is missing from the stack definition.")
        print("Should you with to deploy a stack with no parameters, please define the property as: \n"
              "\"Parameters: {}\"")
        if from_pipeline:
            alert(stack_name,
                  "The Parameters property is missing from the stack "
                  "" + stack_name + " in stack_file " + stack_file + ".\n"
                  "Should you with to deploy a stack with no parameters, please simply define the property as: \n"
                  "Parameters: {}",
                  None, None, action, profile_name, slack_webhook_url)
        exit(1)

    template = None
    try:
        with open(stacks[stack_name]['Template'], 'r') as template_stream:
            template = yaml.safe_load(template_stream)
    except yaml.YAMLError as exc:
        print(exc)
        exit(1)

    if 'Resources' not in template:
        print("The CloudFormation templates provided for this stack does not contain any Resources")
        if from_pipeline:
            alert(stack_name,
                  "The CloudFormation template {} for stack {} does not contain any Resources.".format(
                      stacks[stack_name]['Template'], stack_name),
                  None, None, action, profile_name, slack_webhook_url)
        exit(1)

    # Get auth
    if profile_name is not None:
        try:
            boto3.setup_default_session(profile_name=profile_name)
        except Exception as exc:
            print(exc)
            exit(1)
    # Verify integrity of stack
    stacks = None
    try:
        with open(stack_file, 'r') as stack_stream:
            stacks = yaml.safe_load(stack_stream)
            aws_region = stacks[stack_name]['Region']
            aws_account = stacks[stack_name]['Account']
            stack_template = stacks[stack_name]['Template']
    except yaml.YAMLError as exc:
        print(exc)
        alert(stack_name,
              "Unable to verify required options for stack {} in stack file {}. Exception = {}".format(
                  stack_name, stack_file, exc),
              aws_region, aws_account, action, profile_name, slack_webhook_url)
        exit(1)

    # Connect to AWS CloudFormation
    cf_client = boto3.client('cloudformation', region_name=aws_region)

    # Check if stack exists
    stack_id = None
    try:
        stack_check = cf_client.describe_stacks(
            StackName=stack_name
        )
        stack_id = stack_check['Stacks'][0]['StackId']
    except Exception as exc:
        print(exc)
        alert(stack_name,
              "Unable to check if stack already exists. Exception = {}".format(exc),
              aws_region, aws_account, action, profile_name, slack_webhook_url)
        exit(1)

    # Disable termination protection
    try:
        cf_client.update_termination_protection(StackName=stack_name, EnableTerminationProtection=False)
    except Exception as exc:
        print(exc)
        alert(stack_name,
              "Unable to disable termination protection. Exception = {}".format(exc),
              aws_region, aws_account, action, profile_name, slack_webhook_url)
        exit(1)

    # Delete the stack
    waiter = None
    try:
        cf_client.delete_stack(StackName=stack_name, ClientRequestToken=client_token)
    except Exception as exc:
        print(exc)
        alert(stack_name,
              "Unable to start stack deletion process. Exception = {}".format(exc),
              aws_region, aws_account, action, profile_name, slack_webhook_url)
        exit(1)

    # Waiting for stack to finish deleting
    try:
        waiter = cf_client.get_waiter('stack_delete_complete')
        waiter.wait(StackName=stack_name)
    except Exception as exc:
        pass

    # Check final status of stack
    stack_events = cf_client.describe_stack_events(StackName=stack_id)
    failure_reasons = []
    for resource in stack_events["StackEvents"]:
        if "ClientRequestToken" in resource and \
            client_token == resource["ClientRequestToken"] and \
                "FAILED" in str(resource["ResourceStatus"]):

            failure_reasons.append("- *{}* <> {}".format(resource["LogicalResourceId"],
                                                         resource["ResourceStatusReason"]))
    if len(failure_reasons) > 0:
        print("DELETE_FAILURE for stack {}".format(stack_name))
        alert(stack_name,
              'Stack deletion process ended with status {}.\n'
              'Failure reasons :\n{}'.format(
                  "DELETE_FAILED",
                  "\n".join(failure_reasons)
              ),
              aws_region, aws_account, action, profile_name, slack_webhook_url)
        exit(1)

    print("DELETE_COMPLETE for stack {}".format(stack_name))
    alert(stack_name, None, aws_region, aws_account, "DELETE_COMPLETE", profile_name, slack_webhook_url)

    return True