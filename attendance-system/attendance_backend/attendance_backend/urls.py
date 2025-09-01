from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.http import HttpResponse

def home_view(request):
    return HttpResponse("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Sistema de Asistencia GPS</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; background: #f5f5f5; }
            .container { max-width: 800px; margin: 0 auto; background: white; padding: 40px; border-radius: 10px; box-shadow: 0 4px 15px rgba(0,0,0,0.1); }
            h1 { color: #2c3e50; text-align: center; }
            .status { background: #27ae60; color: white; padding: 15px; border-radius: 5px; text-align: center; margin: 20px 0; }
            .links { display: grid; gap: 15px; margin-top: 30px; }
            .link-card { background: #3498db; color: white; padding: 20px; border-radius: 8px; text-decoration: none; text-align: center; transition: transform 0.3s; }
            .link-card:hover { transform: translateY(-5px); text-decoration: none; color: white; }
            .description { color: #666; line-height: 1.6; margin: 20px 0; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>📍 Sistema de Asistencia con GPS</h1>
            <div class="status">✅ Servidor Django funcionando correctamente</div>
            
            <div class="description">
                <p><strong>Sistema completo de control de asistencia con:</strong></p>
                <ul>
                    <li>✅ Geolocalización GPS exacta</li>
                    <li>✅ Funcionamiento offline con sincronización automática</li>
                    <li>✅ Panel web en tiempo real</li>
                    <li>✅ App móvil React Native</li>
                </ul>
            </div>
            
            <div class="links">
                <a href="/api/health/" class="link-card">
                    🔍 Estado de la API
                </a>
                <a href="/api/panel/" class="link-card">
                    📊 Panel de Control Web
                </a>
                <a href="/admin/" class="link-card">
                    ⚙️ Panel de Administración
                </a>
                <a href="/api/employees/" class="link-card">
                    👥 Lista de Empleados (JSON)
                </a>
                <a href="/api/attendance-records/" class="link-card">
                    📋 Registros de Asistencia (JSON)
                </a>
            </div>
            
            <div style="margin-top: 40px; text-align: center; color: #666; font-size: 0.9em;">
                <p>Para usar la app móvil, asegúrate de actualizar la IP en <code>App.tsx</code></p>
                <p><code>API_BASE_URL = 'http://TU_IP:8000/api'</code></p>
            </div>
        </div>
    </body>
    </html>
    """)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('facial_recognition.urls')),  # ← Aquí cambié 'attendance.urls' por 'facial_recognition.urls'
    path('', home_view, name='home'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)