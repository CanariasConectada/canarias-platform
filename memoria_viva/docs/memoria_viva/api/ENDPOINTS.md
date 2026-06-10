# API REST - Endpoints de Memoria Viva

## Base URL

```
https://guanarteme.canariasconectada.es
```

---

## Comentarios

### Listar Comentarios

**Endpoint**: `GET /memoria-viva/comentario/listar`

**Autenticación**: Pública (no requiere login)

**Parámetros**:
| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|-----------|-------------|
| `lugar_id` | integer | Sí | ID del lugar |
| `offset` | integer | No | Desplazamiento para paginación (default: 0) |
| `limit` | integer | No | Límite de resultados (default: 10) |

**Ejemplo**:
```bash
curl "https://guanarteme.canariasconectada.es/memoria-viva/comentario/listar?lugar_id=2&offset=0&limit=10"
```

**Respuesta exitosa (200)**:
```json
{
  "success": true,
  "comentarios": [
    {
      "id": 36,
      "autor_nombre": "Domingo Santana Santana | ABinformática",
      "autor_imagen_url": "https://.../web/image/res.users/895/avatar_128",
      "contenido": "Hola Mundo - Prueba con commit",
      "fecha": "06/04/2026 20:56",
      "respuestas": []
    }
  ],
  "total": 2,
  "tiene_mas": false
}
```

---

### Enviar Comentario

**Endpoint**: `POST /memoria-viva/comentario/enviar`

**Autenticación**: Requerida (usuario logueado)

**Headers**:
```
Content-Type: application/json
```

**Body**:
```json
{
  "lugar_id": 2,
  "contenido": "Mi comentario",
  "parent_id": null
}
```

**Parámetros**:
| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|-----------|-------------|
| `lugar_id` | integer | Sí | ID del lugar |
| `contenido` | string | Sí | Texto del comentario |
| `parent_id` | integer | No | ID del comentario padre (para respuestas) |

**Respuesta exitosa (200)**:
```json
{
  "success": true,
  "comentario": {
    "id": 37,
    "autor_nombre": "Nombre del Usuario",
    "autor_imagen_url": "https://...",
    "contenido": "Mi comentario",
    "fecha": "06/04/2026 21:00",
    "estado": "aprobado",
    "pendiente_moderacion": false
  }
}
```

**Respuesta sin autenticación (303)**:
```html
Redirecting to /web/login...
```

---

## Lugares

### Listar Lugares

**Endpoint**: `GET /memoria-viva`

**Autenticación**: Pública

**Parámetros opcionales**:
- `search`: Término de búsqueda
- `tipo`: ID del tipo de lugar
- `categoria`: ID de la categoría

---

### Ver Detalle de Lugar

**Endpoint**: `GET /memoria-viva/<slug>`

**Autenticación**: Pública

**Ejemplo**:
```bash
curl "https://guanarteme.canariasconectada.es/memoria-viva/playa-el-confital"
```

---

## Likes

### Dar Like

**Endpoint**: `POST /memoria-viva/like/<lugar_id>`

**Autenticación**: Pública (con cookie de sesión)

**Ejemplo**:
```bash
curl -X POST "https://guanarteme.canariasconectada.es/memoria-viva/like/2" \
  -H "Content-Type: application/json" \
  -d '{}'
```

**Respuesta**:
```json
{
  "success": true,
  "like_count": 5,
  "already_liked": false
}
```

---

## Códigos de Error

| Código | Significado |
|--------|-------------|
| 200 | Éxito |
| 302/303 | Redirección (login requerido) |
| 400 | Error en solicitud |
| 401 | No autorizado |
| 403 | Prohibido |
| 404 | Recurso no encontrado |
| 500 | Error interno del servidor |

---

## Notas

- Todas las respuestas son en formato JSON
- Las fechas están en formato `"DD/MM/YYYY HH:MM"`
- Las imágenes de avatar son URLs accesibles públicamente
- El estado de comentarios puede ser: `pendiente`, `aprobado`, `rechazado`
