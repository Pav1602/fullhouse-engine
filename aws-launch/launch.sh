#!/bin/bash
# Launch a c7i.48xlarge EC2 instance for the skb79 sweep.
# REQUIRES: quota L-1216C47A (on-demand Standard vCPUs) raised to >=192
#       OR  quota L-34B43A08 (spot Standard vCPUs) raised to >=192 if using spot
#
# Before running this script:
#   1. Create a keypair (one-time):
#      aws ec2 create-key-pair --key-name skb-sweep-key --region eu-west-2 \
#        --query 'KeyMaterial' --output text > ~/.ssh/skb-sweep-key.pem
#      chmod 400 ~/.ssh/skb-sweep-key.pem
#
#   2. Create a security group allowing SSH from your IP (one-time):
#      MY_IP=$(curl -s https://checkip.amazonaws.com)
#      aws ec2 create-security-group --group-name skb-sweep-sg \
#        --description "SSH from my IP for skb sweep" --region eu-west-2
#      aws ec2 authorize-security-group-ingress --group-name skb-sweep-sg \
#        --protocol tcp --port 22 --cidr ${MY_IP}/32 --region eu-west-2
#
#   3. Verify quota L-1216C47A is >=192 (for on-demand) — check the AWS console
#      or:  aws service-quotas get-service-quota --service-code ec2 \
#             --quota-code L-1216C47A --region eu-west-2
set -euo pipefail

REGION=${REGION:-eu-west-2}
INSTANCE_TYPE=${INSTANCE_TYPE:-c7i.48xlarge}
KEY_NAME=${KEY_NAME:-skb-sweep-key}
SG_NAME=${SG_NAME:-skb-sweep-sg}
USE_SPOT=${USE_SPOT:-0}    # 1 = spot (~$1.84/hr), 0 = on-demand (~$8.57/hr, no interruption risk)

# Latest Ubuntu 24.04 LTS AMI in REGION
AMI_ID=$(aws ec2 describe-images \
    --owners 099720109477 \
    --filters "Name=name,Values=ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*" \
              "Name=state,Values=available" \
    --query 'Images | sort_by(@, &CreationDate) | [-1].ImageId' \
    --output text --region $REGION)
echo "Using AMI: $AMI_ID"

SG_ID=$(aws ec2 describe-security-groups --group-names $SG_NAME --region $REGION \
        --query 'SecurityGroups[0].GroupId' --output text)
echo "Using security group: $SG_ID"

USER_DATA=$(base64 -w0 < "$(dirname "$0")/user-data.sh")

LAUNCH_ARGS=(
    --image-id "$AMI_ID"
    --instance-type "$INSTANCE_TYPE"
    --key-name "$KEY_NAME"
    --security-group-ids "$SG_ID"
    --user-data "$USER_DATA"
    --block-device-mappings 'DeviceName=/dev/sda1,Ebs={VolumeSize=50,VolumeType=gp3,DeleteOnTermination=true}'
    --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=skb-sweep-79},{Key=Purpose,Value=skantbot-sweep}]'
    --instance-initiated-shutdown-behavior terminate
    --region "$REGION"
    --count 1
)

if [ "$USE_SPOT" = "1" ]; then
    LAUNCH_ARGS+=( --instance-market-options 'MarketType=spot,SpotOptions={SpotInstanceType=one-time}' )
    echo "Launching SPOT instance (cheaper but interruptible)..."
else
    echo "Launching ON-DEMAND instance (no interruption risk)..."
fi

aws ec2 run-instances "${LAUNCH_ARGS[@]}" \
    --query 'Instances[0].[InstanceId,PublicIpAddress,InstanceLifecycle,InstanceType]' \
    --output table

echo ""
echo "Instance launching. Wait ~3 min for cloud-init to finish, then:"
echo "  1. Find the public IP from the table above"
echo "  2. ssh -i ~/.ssh/${KEY_NAME}.pem ubuntu@<IP>"
echo "  3. From your local machine, in another terminal:"
echo "     rsync -avz --exclude='.venv' --exclude='__pycache__' --exclude='*.db' \\"
echo "       ~/Projects/Poker-bot/fullhouse-engine/ ubuntu@<IP>:fullhouse-engine/"
echo "  4. On instance: tmux new -s sweep ; bash fullhouse-engine/aws-launch/run-sweep.sh"
echo "  5. Detach: Ctrl-b d  (sweep runs in background)"
echo "  6. When done, from local:"
echo "     rsync -avz ubuntu@<IP>:fullhouse-engine/harness/results/ ~/Projects/Poker-bot/fullhouse-engine/harness/results/"
echo "  7. TERMINATE the instance:"
echo "     aws ec2 terminate-instances --instance-ids <INSTANCE_ID> --region $REGION"
