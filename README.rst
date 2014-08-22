**A simple script that simulates user's basic workflow in OpenStack**

1. Creates network, subnet, router
2. Allocates a floating IP to the project
3. Creates an SSH key
4. Creates an instance and assigns a floating IP to it
5. Tries to SSH to the instance and run `ping google.com` inside of it
6. Deletes everything created earlier

There are certain timeout values configured in the script:

1. Instance creation - 120 seconds
2. SSH into the instance - 60 seconds
4. Instance deletion - 300 seconds
