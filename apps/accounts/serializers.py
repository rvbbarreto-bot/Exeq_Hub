from rest_framework import serializers


class LoginSerializer(serializers.Serializer):
    tenant_slug = serializers.SlugField(max_length=64)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)
