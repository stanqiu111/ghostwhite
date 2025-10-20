from django.shortcuts import render, redirect


def home_view(request):
    """
    Home page - shows home.html
    Requires authentication
    """
    if not request.user.is_authenticated:
       return redirect("authors_pages:auth_page")  # Redirect to login

    return render(request, "home.html")
