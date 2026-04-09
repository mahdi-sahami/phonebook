from .models import Contact
from rest_framework.response import Response
from rest_framework import status
from rest_framework.request import Request
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.generics import ListAPIView, CreateAPIView, ListCreateAPIView
from rest_framework.viewsets import ViewSet, ModelViewSet
from . import serializers
from drf_yasg.utils import swagger_auto_schema


class ContactView(APIView):
    permission_classes = [IsAuthenticated]


    def get(self, request: Request):
        contacts = Contact.objects.filter(owner=request.user)
        serializer = serializers.ContactSerializer(contacts, many=True)
        return Response(serializer.data)

    @swagger_auto_schema(request_body=serializers.CreateContactSerializer)
    def post(self, request: Request):

        serializer = serializers.CreateContactSerializer(data=request.data, context={"request": request})
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    
    def put(self, request: Request, id: int):
        try:
            contact = Contact.objects.get(owner=request.user, id=id)
        except Contact.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        serializer = serializers.UpdateContactSerializer(contact, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    

    def delete(self, request: Request, id: int):
        try:
            contact = Contact.objects.get(owner=request.user, id=id)
        except Contact.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        contact.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class RegisterView(APIView):
    def post(self, request):
        serializer = serializers.RegisterSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response({"message": "User created"})
        return Response(serializer.errors, status=400)

