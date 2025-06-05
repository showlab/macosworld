# Release AWS Environment

Once the benchmark has completed, you need to manually terminate the instance and then release the host. Before proceeding, please note the following important points:

1. You can use one instance ID to complete all benchmark tasks, so there is no need to terminate an instance unless you want to release the dedicated host.
2. After terminating an instance, due to AWS's cleanup mechanism, you must wait approximately 20 minutes before you can release the host, or about 1 hour before you can launch a new instance.
3. To meet compliance requirements, dedicated hosts can only be released 24 hours after they have been allocated.

## Terminate instance

First, let's terminate the instance. Navigate to https://console.aws.amazon.com/ec2 and go to the "Instances" panel. Select the checkbox next to the instance you want to terminate.

![](../assets/release_aws_env/screenshot%20(33).JPG)

In the "Instance state" drop-down menu, click "Terminate (delete) instance".

![](../assets/release_aws_env/screenshot%20(34).JPG)

Click "Terminate (delete)" to confirm.

![](../assets/release_aws_env/screenshot%20(35).JPG)

You will see a banner notification indicating that the instance is beginning the termination process. The next step is to release the dedicated host. However, you typically need to wait approximately 20 minutes before proceeding to the next step.

![](../assets/release_aws_env/screenshot%20(36).JPG)

## Release dedicated host

Navigate to "Dedicated hosts" from the left sidebar, then select the host machine you want to release.

![](../assets/release_aws_env/screenshot%20(37).JPG)

Right-click on your selection and click "Release host". 

![](../assets/release_aws_env/screenshot%20(38).JPG)

Click "Release" to confirm.

![](../assets/release_aws_env/screenshot%20(39).JPG)

Once you see a success banner, the host has been released successfully. Note that it may continue to appear in your dedicated hosts list for several hours even after being released.

![](../assets/release_aws_env/screenshot%20(40).JPG)

If the release fails, wait some time and try again. Typically, a host can be released approximately 20 minutes after you initiate instance termination.

