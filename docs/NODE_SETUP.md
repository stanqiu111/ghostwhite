# Connecting nodes

[Documentation index](README.md) · [Inbox protocol](INBOX_API_FLOW.md) · [Live-stream federation](FEDERATED_STREAMING.md)

## Setup

### 1. Configure Your Local Node
- Django Admin → Nodes → Find your local node (`is_local = True`)
- Set the canonical `host_url`, `username` and `password`. Your server sends these local credentials on outbound federation requests. Each peer must register them against your remote-node record.

### 2. Add Remote Node
- Django Admin → Nodes → Add Node
- Set:
  - `host_url`: Remote node's base URL (include path prefix if needed, e.g., `/socialdistribution/`)
  - `is_local`: False
  - `is_active`: True
  - `is_disabled`: False
  - `username`: Remote node's username
  - `password`: Remote node's password

### 3. Ask Remote Admin to Add Your Node
- They need to add your node with your credentials from step 1

---

## Shell access

Run the local command below in the configured virtual environment. For an existing, authorized Heroku deployment only, prefix it with `heroku run --app <your-app>`. This guide does not imply that a deployment is configured or authorize production changes.

```bash
python manage.py shell
```

---

## List Local Authors

```python
from authors.models import Author

for author in Author.objects.filter(node__is_local=True):
    print(f"{author.username} ({author.display_name or 'N/A'})")
    print(f"  ID: {author.id}\n")
```

---

## List Remote Authors

```python
from nodes.models import Node
import requests
from requests.auth import HTTPBasicAuth

# Set remote node URL
node_url = "https://peer.example/"
node = Node.objects.get(host_url=node_url, is_local=False)
local_node = Node.objects.get(is_local=True)

response = requests.get(
    f"{node_url.rstrip('/')}/api/authors",
    auth=HTTPBasicAuth(local_node.username, local_node.password),
    headers={"Content-Type": "application/json"},
    timeout=10
)
response.raise_for_status()

data = response.json()
authors = data.get("authors", []) if isinstance(data, dict) else data

for author in authors:
    name = author.get('displayName') or author.get('username', 'N/A')
    print(f"{name}")
    print(f"  FQID: {author.get('id', 'N/A')}\n")
```

---

## Send Follow Request

```python
from authors.models import Author, Follow
from utils.node_communication import send_follow_request_to_remote_node, get_or_create_remote_author
from utils.fqid import parse_author_fqid
from nodes.models import Node
import requests
from requests.auth import HTTPBasicAuth

# Set these values
your_author_id = "YOUR_LOCAL_AUTHOR_FQID"
remote_author_fqid = "REMOTE_AUTHOR_FQID"

# Get your author
your_author = Author.objects.get(id=your_author_id)

# Parse remote author FQID and get remote node
full_fqid, node_url = parse_author_fqid(remote_author_fqid)
remote_node = Node.objects.get(host_url=node_url, is_local=False)
local_node = Node.objects.get(is_local=True)
local_node = Node.objects.get(is_local=True)

# Fetch remote author data
author_url = full_fqid.rstrip('/') + '/'
try:
    response = requests.get(
        author_url,
        auth=HTTPBasicAuth(local_node.username, local_node.password),
        headers={"Content-Type": "application/json"},
        timeout=10
    )
    response.raise_for_status()
    author_data = response.json()
    remote_author_fqid = author_data.get('id', full_fqid)
except requests.exceptions.HTTPError:
    author_data = {"id": full_fqid, "displayName": "", "github": ""}
    remote_author_fqid = full_fqid

# Create/get remote author
remote_author, _ = get_or_create_remote_author(remote_author_fqid, author_data, remote_node)

# Create follow request
follow, created = Follow.objects.get_or_create(
    follower=your_author,
    following=remote_author,
    defaults={"approved": False, "status": Follow.PENDING}
)

# Send follow request
send_follow_request_to_remote_node(follow)
print(f"✓ Follow request sent! (status: {follow.status})")
```

## Live-stream support

Ordinary inbox federation does not provide a player. Both Ghostwhite nodes must
include the streaming extension, and third-party applications must implement
its contract. Follow [federated streaming](FEDERATED_STREAMING.md) for reciprocal
setup, server-only credential handling, TURN, and actual media acceptance.
