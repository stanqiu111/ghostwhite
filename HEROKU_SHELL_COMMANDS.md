# Connecting Two Nodes - Quick Guide

## Prerequisites

1. **Update YOUR node credentials in Django Admin:**
   - Go to Django Admin → Nodes
   - Find your local node (is_local = True)
   - Set `username` and `password` (these are YOUR node's credentials that other nodes will use to authenticate with you)
   - Save

2. **Add the external node in Django Admin:**
   - Go to Django Admin → Nodes
   - Click "Add Node"
   - Set:
     - `host_url`: The external node's URL (e.g., `https://ghostwhite-ximeng-c739441113d7.herokuapp.com/`)
     - `is_local`: False
     - `username`: The external node's username (for you to authenticate with them)
     - `password`: The external node's password
   - Save

3. **Ask the external node admin to add YOUR node:**
   - They need to add your node in their Django Admin with:
     - `host_url`: Your node's URL
     - `is_local`: False
     - `username`: YOUR node's username (from step 1)
     - `password`: YOUR node's password (from step 1)

---

---

## List Local Authors (Your Authors)

```python
from authors.models import Author

print("Local Authors:")
for author in Author.objects.filter(node__is_local=True):
    print(f"  {author.username} ({author.display_name or 'N/A'})")
    print(f"    ID: {author.id}")
    print()
```

**Example output:**
```
Local Authors:
  evelyn_local_node (Evelyn)
    ID: a3ab10db-bba4-402a-bc05-e9b60a78f7ac
```

---

## List Remote Authors (External Node Authors)

```python
from nodes.models import Node
import requests
from requests.auth import HTTPBasicAuth

# Replace with your external node URL
node_url = "https://ghostwhite-ximeng-c739441113d7.herokuapp.com/"
node = Node.objects.get(host_url=node_url, is_local=False)

response = requests.get(
    f"{node_url.rstrip('/')}/api/authors/",
    auth=HTTPBasicAuth(node.username, node.password),
    headers={"Content-Type": "application/json"},
    timeout=10
)
response.raise_for_status()

data = response.json()
authors = data.get("authors", []) if isinstance(data, dict) else data

print(f"Remote Authors from {node_url}:")
for author in authors:
    name = author.get('displayName') or author.get('username', 'N/A')
    author_id = author.get('id', 'N/A')
    print(f"  {name}")
    print(f"    FQID: {author_id}")
    print()
```

**Example output:**
```
Remote Authors from https://ghostwhite-ximeng-c739441113d7.herokuapp.com/:
  Ximeng
    FQID: https://ghostwhite-ximeng-c739441113d7.herokuapp.com/api/authors/32ebf933-4f67-4987-8f0d-9645cebec63b/
```

## Send Follow Request

Run: `heroku run python manage.py shell`

Then copy-paste this entire block:

```python
from authors.models import Author, Follow
from utils.node_communication import send_follow_to_remote_node, get_or_create_remote_author
from nodes.models import Node
import requests
from requests.auth import HTTPBasicAuth

# Replace these with actual values
your_author_id = "YOUR_AUTHOR_UUID"  # Your local author's UUID
remote_author_fqid = "https://external-node.com/api/authors/REMOTE_AUTHOR_UUID/"  # Remote author's full URL

# Get your author
your_author = Author.objects.get(id=your_author_id)
print(f"Following from: {your_author.username}")

# Fetch and create remote author
node_url = remote_author_fqid.split('/api/authors/')[0] + '/'
remote_node = Node.objects.get(host_url=node_url, is_local=False)

response = requests.get(
    remote_author_fqid,
    auth=HTTPBasicAuth(remote_node.username, remote_node.password),
    headers={"Content-Type": "application/json"},
    timeout=10
)
response.raise_for_status()
author_data = response.json()

remote_author, created = get_or_create_remote_author(remote_author_fqid, author_data, remote_node)
print(f"Remote author: {remote_author.display_name or remote_author.username}")

# Create follow request
follow, created = Follow.objects.get_or_create(
    follower=your_author,
    following=remote_author,
    defaults={"approved": False, "status": Follow.PENDING}
)

print(f"Follow request {'created' if created else 'already exists'} (status: {follow.status})")

# Send follow request to remote node
send_follow_to_remote_node(follow)
print("✓ Follow request sent! Check the remote node to see if it was received.")
```
