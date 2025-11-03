from django import forms
from .models import GitHubIntegration

class GitHubIntegrationForm(forms.ModelForm):
    class Meta:
        model = GitHubIntegration
        fields = ("github_username",)  # only username, no access token
        help_texts = {
            "github_username": "Your public GitHub username",
        }
