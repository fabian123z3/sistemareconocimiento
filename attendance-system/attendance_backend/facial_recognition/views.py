# AGREGAR ESTA FUNCIÓN AL INICIO DE facial_recognition/views.py

@api_view(['GET'])
def health_check(request):
    """
    Endpoint de salud para verificar que la API está funcionando
    """
    return Response({
        'status': 'OK',
        'message': 'Facial Recognition API is running',
        'timestamp': datetime.now().isoformat()
    }, status=status.HTTP_200_OK)