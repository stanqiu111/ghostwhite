"""
Node-to-node HTTP Basic Authentication

References:
- Django REST Framework Custom Authentication:
  https://www.django-rest-framework.org/api-guide/authentication/#custom-authentication
- HTTP Basic Authentication (RFC 7617):
  https://datatracker.ietf.org/doc/html/rfc7617
"""
from rest_framework import authentication, exceptions, permissions
from nodes.models import Node
import base64


class NodeBasicAuthentication(authentication.BaseAuthentication):
    """Authenticates using Node credentials for node-to-node communication"""
    
    def authenticate(self, request):
        """
        Authenticate the request using HTTP Basic Authentication.
        
        Returns (node, None) on success, None if no Basic auth header, 
        raises AuthenticationFailed on invalid credentials.
        """
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        if not auth_header.startswith('Basic '):
            return None
        
        try:
            encoded = auth_header.split(' ', 1)[1]
            decoded = base64.b64decode(encoded).decode('utf-8')
            username, password = decoded.split(':', 1)
        except (ValueError, UnicodeDecodeError):
            raise exceptions.AuthenticationFailed('Invalid auth header')
        
        try:
            node = Node.objects.get(username=username, password=password)
            node.is_authenticated = True
            return (node, None)
        except Node.DoesNotExist:
            raise exceptions.AuthenticationFailed('Invalid node credentials')


class NodeAuthenticated(permissions.BasePermission):
    """Permission class that allows authenticated nodes"""
    
    def has_permission(self, request, view):
        return (
            request.user and 
            hasattr(request.user, 'is_authenticated') and 
            request.user.is_authenticated
        )

