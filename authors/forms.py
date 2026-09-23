from django import forms
from django.contrib.auth import password_validation

from .models import Author


class ProfileSettingsForm(forms.ModelForm):
    class Meta:
        model = Author
        fields = ["display_name", "bio", "github_url", "image", "profile_visibility"]
        labels = {"profile_visibility": "Who can see my profile"}
        help_texts = {
            "profile_visibility": (
                "Your username and display name stay visible so people can still "
                "find you and see who wrote a post. This controls your bio, "
                "GitHub link, avatar and follower lists. Who can read each post "
                "is set per post when you write it."
            ),
        }
        widgets = {
            "display_name": forms.TextInput(attrs={"class": "settings-input"}),
            "bio": forms.Textarea(attrs={"class": "settings-input", "rows": 3}),
            "github_url": forms.URLInput(attrs={"class": "settings-input", "placeholder": "https://github.com/username"}),
            "profile_visibility": forms.Select(attrs={"class": "settings-input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # A POST that omits this field (an older form, or a partial submit)
        # must leave the existing privacy setting alone rather than fail
        # validation or reset it.
        self.fields["profile_visibility"].required = False

    def clean_profile_visibility(self):
        value = self.cleaned_data.get("profile_visibility")
        if not value:
            return self.instance.profile_visibility
        return value


class EmailChangeForm(forms.Form):
    email = forms.EmailField(
        label="Email address",
        widget=forms.EmailInput(attrs={"class": "settings-input"}),
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        qs = Author.objects.filter(email__iexact=email)
        if self.user:
            qs = qs.exclude(pk=self.user.pk)
        if qs.exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email


class PasswordChangeForm(forms.Form):
    current_password = forms.CharField(
        label="Current password",
        widget=forms.PasswordInput(attrs={"class": "settings-input"}),
    )
    new_password1 = forms.CharField(
        label="New password",
        widget=forms.PasswordInput(attrs={"class": "settings-input"}),
    )
    new_password2 = forms.CharField(
        label="Confirm new password",
        widget=forms.PasswordInput(attrs={"class": "settings-input"}),
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean_current_password(self):
        pw = self.cleaned_data["current_password"]
        if self.user and not self.user.check_password(pw):
            raise forms.ValidationError("Current password is incorrect.")
        return pw

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get("new_password1")
        p2 = cleaned.get("new_password2")
        if p1 and p2 and p1 != p2:
            self.add_error("new_password2", "Passwords don't match.")
        if p1:
            try:
                password_validation.validate_password(p1, self.user)
            except forms.ValidationError as e:
                self.add_error("new_password1", e)
        return cleaned
