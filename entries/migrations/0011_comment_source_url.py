from django.db import migrations, models


def populate_comment_source_urls(apps, schema_editor):
    Comment = apps.get_model("entries", "Comment")
    Author = apps.get_model("authors", "Author")
    Node = apps.get_model("nodes", "Node")
    try:
        local_node = Node.objects.get(is_local=True)
    except Node.DoesNotExist:
        local_node = None

    if not local_node:
        return

    base = local_node.host_url.rstrip("/")

    comments = Comment.objects.filter(source_url__isnull=True)
    author_ids = comments.values_list("author_id", flat=True)
    authors = {
        a.id: a
        for a in Author.objects.filter(id__in=author_ids).select_related("node")
    }

    for comment in comments:
        author = authors.get(comment.author_id)
        if not author:
            continue
        if author.node_id != local_node.id:
            continue
        comment.source_url = f"{base}/api/authors/{comment.author_id}/commented/{comment.id}"
        comment.save(update_fields=["source_url"])


class Migration(migrations.Migration):
    dependencies = [
        ("entries", "0010_comment_comment_entry_created_idx_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="comment",
            name="source_url",
            field=models.URLField(blank=True, null=True),
        ),
        migrations.RunPython(populate_comment_source_urls, migrations.RunPython.noop),
    ]

