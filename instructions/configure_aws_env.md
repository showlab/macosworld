# Configure AWS Environment for macOSWorld

macOSWorld requires renting an AWS-hosted cloud server and launching an instance on it. The clould environment setup mainly consists of three main steps:
1. Register and configure your AWS account
2. Create a dedicated host
3. Create a macOS instance

## AWS account configuration

### Account setup

 - Create an AWS root user account by registering at [this link](https://portal.aws.amazon.com/billing/signup)
 - Setup billing information for your account (see the [AWS billing documentation](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/billing-getting-started.html) for guidance)

### Service limits

 - In the Asia Pacific (Singapore) ap-southeast-1 region, increase your account's "Running Dedicated mac2 Hosts" limit to 1 or higher
 - To request a limit increase, visit [this link](https://ap-southeast-1.console.aws.amazon.com/servicequotas/home/services/ec2/quotas/L-5D8DADF5) and click "Request increase at account level"

### Access keys
 - Create account access keys following the [tutorial](https://docs.aws.amazon.com/IAM/latest/UserGuide/id-credentials-access-keys-update.html)

## Create a dedicated host

An Amazon EC2 Dedicated Host is a physical server fully dedicated for your use, so you can help address compliance requirements. To begin with, navigate to https://console.aws.amazon.com/ec2. Then in the left side bar, click "Dedicated Hosts".

![](../assets/configure_aws_env/screenshot%20(2).JPG)

Click "Allocate Dedicated Host".

![](../assets/configure_aws_env/screenshot%20(3).JPG)

Under "Name tag", give a name to your dedicated host, for example, `mac2_20250523`.

![](../assets/configure_aws_env/screenshot%20(4).JPG)

Next, under "Instance family", select `mac2` in the drop-down menu. 

![](../assets/configure_aws_env/screenshot%20(5).JPG)

Under "Instance type", choose `mac2.metal` as the instance type. Typically this would be the only option.

![](../assets/configure_aws_env/screenshot%20(6).JPG)

Under "Availability zone", choose `ap-southeast-1a`. 

![](../assets/configure_aws_env/screenshot%20(7).JPG)

Our configurations are complete. Scroll down to the bottom and click "Allocate". 

![](../assets/configure_aws_env/screenshot%20(8).JPG)

Since we are allocating a physical Mac mini machine, pricing would start the moment we click "Allocate". To meet compliance requirements, the dedicated host could be released 24 hours after allocation.

Once the dedicated host is successfully created, note down its host id. We can now move on to creating an instance by clicking "Instances" in the left side bar.

![](../assets/configure_aws_env/screenshot%20(9).JPG)

## Create a macOS instance

To create an instance, click "Launch instances".

![](../assets/configure_aws_env/screenshot%20(10).JPG)

Under "Name and tags", give a name to the instance, for example, `macOS_20250523`.

![](../assets/configure_aws_env/screenshot%20(11).JPG)

We now need to select a template image for the instance. You can simply click macOS and then select "Sequoia". 

![](../assets/configure_aws_env/screenshot%20(12).JPG)

Alternatively, you can click "Browse more AMIs" and select a macOSWorld template, whose AMI IDs could be found in `constants.py`. At this step, it doesn't matter which `mac2.metal` AMI is launched, because when benchmarking each task later, the testbench will automatically replace it with the required template image.

Scroll down to "Key pair (login)". If this is the first time you are launching an instance, click "Create new key pair". 

![](../assets/configure_aws_env/screenshot%20(14).JPG)

Give a name to your key pair. Set the key pair type to RSA and the file format to `.pem`. Then, click "Create key pair". This key pair could also be kept for future use.

![](../assets/configure_aws_env/screenshot%20(15).JPG)

If you have previously created a key pair, simply select that under the drop-down menu. As required by the testbench, DO NOT proceed without a key pair.

![](../assets/configure_aws_env/screenshot%20(16).JPG)

Next, scroll down to "Network settings". If this is your time time creating an instance, click "Create security group". It would be easier to simply allow SSH traffic from anywhere. Otherwise, make sure to allow SSH traffic from where you would run the benchmark.

![](../assets/configure_aws_env/screenshot%20(17).JPG)

If you have previously created a security group, you can re-use it. Click "Select existing security group". Then, under the "Common security groups" drop-down menu, select the security group you would like to re-use.

![](../assets/configure_aws_env/screenshot%20(18).JPG)

We now need to link the instance to the host machine we have previously allocated. To do this, scroll down to the bottom and expand "Advanced details". 

![](../assets/configure_aws_env/screenshot%20(19).JPG)

Under "Tenancy", select "Dedicated host".

![](../assets/configure_aws_env/screenshot%20(20).JPG)

Under "Target host by", select "Host ID".

![](../assets/configure_aws_env/screenshot%20(21).JPG)

Then, under "Tenancy host ID", select the machine that we have previously allocated. We can compare the ID displayed here to the one we have previously noted down.

![](../assets/configure_aws_env/screenshot%20(22).JPG)

Click "Launch instance" on the right.

![](../assets/configure_aws_env/screenshot%20(23).JPG)

It will take less than a minute for the instance to start. Do not leave the page.

![](../assets/configure_aws_env/screenshot%20(24).JPG)

Once we see the launching success notification, note down the instance ID. This ID would be required by the testbench. Following this, click "Connect to instance".

![](../assets/configure_aws_env/screenshot%20(25).JPG)

Navigate to the SSH client panel. Here, the instance's public DNS would be listed. Note this down.

![](../assets/configure_aws_env/screenshot%20(26).JPG)

This finishes the environment configuration. Let's now wait for 10 minutes before starting the testbench. 

---

Meanwhile, if you want to play with the environment, you may ssh into it or remotely control it through VNC. If you started an official AMI, then follow the instructions [here](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/connect-to-mac-instance.html) to establish SSH/VNC connections to the instance. If you started a macOSWorld template, then you can establish remote connection with username `ec2-user` and password `000000`.

> **📌 Important Remarks**  
> When playing with the environment, please avoid shutting down the machine whenever possible (rebooting is acceptable). This is because a shutdown automatically triggers a cleanup process, which occupies the dedicated host for approximately one hour. In other words, if the machine is shut down (including terminating an instance), it cannot be restarted for about an hour.
