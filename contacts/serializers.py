
from rest_framework import serializers
from .models import Contact
from django.contrib.auth.models import User


class CreateContactSerializer(serializers.ModelSerializer):
    owner = serializers.HiddenField(default=serializers.CurrentUserDefault())
    class Meta:
        model = Contact
        fields = ["owner", "name", "phone", "email", "address"]  
       

class ContactSerializer(serializers.ModelSerializer):
    class Meta:
        model = Contact
        fields = "__all__"

class CreateUserSerializer(serializers.ModelSerializer):   

    class Meta:
        model = Contact
        fields = ['username', 'email', 'password']

class UpdateContactSerializer(serializers.ModelSerializer):
    class Meta:
        model = Contact
        fields = ['name', 'phone', 'email', 'address']


class RegisterSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["username", "password"]
        extra_kwargs = {
            "password": {"write_only": True}
        }

    def create(self, validated_data):
        user = User.objects.create_user(
            username=validated_data["username"],
            password=validated_data["password"]
        )
        return user

