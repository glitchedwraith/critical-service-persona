# Deploying the public demo to EC2

One t3.small instance in us-east-1:

```
browser ─▶ :80 nginx ─┬─ /       static frontend (built on your laptop)
                      └─ /api/*  127.0.0.1:3000  scripts/run_local.py   (systemd: truesignal-api)
                                     ├─ DynamoDB Local, in-memory, 127.0.0.1:8000 (systemd: dynamodb-local)
                                     └─ Amazon Bedrock, with credentials from /etc/truesignal/aws.env
```

Each browser gets its own seeded copy of the demo (see `backend/sessions.py`). nginx rate-limits each IP: Bedrock-backed routes 30/min (burst 20), reset 10/min, everything else 10/s.

## Commands

All of them run from the repo root on your laptop, using the AWS credentials in your shell or in `.env`.

| Command | What it does |
|---|---|
| `deploy/provision.sh` | Creates the key pair (`deploy/truesignal-demo.pem`), security group (ports 22 and 80 open to all), instance and Elastic IP, then waits for the bootstrap. Writes `deploy/.instance`. |
| `deploy/ship.sh` | Builds the frontend and runs its tests, rsyncs the app, installs the systemd units and nginx config, restarts the API, and checks the public URL. Re-run after every change. |
| `deploy/push-creds.sh` | Sends the current Bedrock credentials over SSH (never as arguments, never echoed) and restarts the API. Re-run whenever the workshop credentials rotate. The red **AI offline** pill tells you it's time. |
| `deploy/add-ssh-key.sh <file.pub>` | Gives a teammate SSH access with their own key. |
| `deploy/destroy.sh` | Deletes everything `provision.sh` created. Asks you to type the instance ID. |

First deploy: `deploy/provision.sh && deploy/ship.sh && deploy/push-creds.sh`, then open the printed URL.

## On the instance

```sh
ssh -i deploy/truesignal-demo.pem ec2-user@<host>
sudo journalctl -u truesignal-api -f        # API log
sudo systemctl restart dynamodb-local       # wipes all data; the API restarts and reseeds
```

`ship.sh` and `push-creds.sh` restart the API, which reseeds the shared tables. Visitors' private sessions survive. The demo is plain HTTP on the instance's public DNS name.
