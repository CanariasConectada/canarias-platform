# Modelos de Datos - Backend

## Diagrama de Relaciones

```
memoria.viva.historia
    │
    ├── has many ──► memoria.viva.comentario
    │
    └── has many ──► memoria.viva.like

memoria.viva.comentario
    │
    ├── belongs to ──► memoria.viva.historia
    ├── belongs to ──► res.users (autor)
    ├── belongs to ──► memoria.viva.comentario (parent_id)
    └── has many ──► memoria.viva.comentario (respuesta_ids)

memoria.viva.palabra.prohibida
    └── belongs to ──► memoria.viva.settings
```

---

## memoria.viva.comentario

**Descripción**: Sistema de comentarios con moderación.

### Campos

| Campo | Tipo | Requerido | Descripción |
|-------|------|-----------|-------------|
| `lugar_id` | Many2one | Sí | Lugar al que pertenece |
| `autor_id` | Many2one | Sí | Usuario que comenta |
| `autor_nombre` | Char | Auto | Nombre del autor (related) |
| `autor_imagen` | Binary | No | Avatar en base64 |
| `autor_imagen_url` | Char | Compute | URL del avatar |
| `contenido` | Text | Sí | Texto del comentario |
| `estado` | Selection | Sí | `pendiente`, `aprobado`, `rechazado` |
| `contiene_palabras_prohibidas` | Boolean | Auto | Flag de moderación |
| `parent_id` | Many2one | No | Comentario padre (respuestas) |
| `respuesta_ids` | One2many | Auto | Respuestas al comentario |
| `fecha_moderacion` | Datetime | No | Fecha de moderación |
| `moderado_por` | Many2one | No | Usuario que moderó |

### Métodos

#### create(vals_list)
Crea comentarios verificando palabras prohibidas.

```python
comentario = env['memoria.viva.comentario'].create({
    'lugar_id': 1,
    'autor_id': user.id,
    'contenido': 'Mi comentario',
})
```

**Lógica**:
1. Verifica palabras prohibidas en el contenido
2. Si encuentra: estado = 'pendiente', flag = True
3. Si no: estado = 'aprobado'
4. Notifica a moderadores si está pendiente

---

#### action_aprobar()
Aprueba un comentario pendiente.

```python
comentario.action_aprobar()
```

**Efectos**:
- Cambia estado a 'aprobado'
- Registra fecha y moderador
- El comentario aparece en frontend

---

#### action_rechazar()
Rechaza un comentario.

```python
comentario.action_rechazar()
```

**Efectos**:
- Cambia estado a 'rechazado'
- No aparece en frontend

---

#### get_comentarios_aprobados(lugar_id, offset=0, limit=10)
Retorna comentarios para el frontend.

```python
comentarios = Comentario.get_comentarios_aprobados(1, 0, 10)
```

**Retorno**:
```python
[
    {
        'id': 1,
        'autor_nombre': 'Nombre',
        'autor_imagen_url': 'https://...',
        'contenido': 'Texto',
        'fecha': 'DD/MM/YYYY HH:MM',
        'respuestas': [...]
    }
]
```

---

## memoria.viva.palabra.prohibida

**Descripción**: Lista de palabras para moderación automática.

### Campos

| Campo | Tipo | Requerido | Descripción |
|-------|------|-----------|-------------|
| `name` | Char | Sí | La palabra prohibida |
| `active` | Boolean | No | Activa/inactiva |
| `settings_id` | Many2one | No | Configuración asociada |

### Uso

```python
# Crear palabra prohibida
Palabra = env['memoria.viva.palabra.prohibida']
Palabra.create({'name': 'spam', 'active': True})

# Buscar palabras activas
prohibidas = Palabra.search([('active', '=', True)])
```

---

## memoria.viva.settings

**Descripción**: Configuración del módulo.

### Campos de Comentarios

| Campo | Tipo | Default | Descripción |
|-------|------|---------|-------------|
| `permitir_comentarios` | Boolean | True | Activar/desactivar sistema |
| `comentarios_por_pagina` | Integer | 10 | Límite de paginación |
| `palabra_prohibida_ids` | One2many | - | Palabras prohibidas |

### Métodos

#### get_settings()
Retorna configuración singleton.

```python
settings = env['memoria.viva.settings'].get_settings()
print(settings.permitir_comentarios)  # True/False
```

---

## Herencia de mail.thread

El modelo `memoria.viva.comentario` hereda de `mail.thread`:

**Ventajas**:
- Seguimiento de cambios en chatter
- Notificaciones automáticas
- Historial de actividades

**Uso**:
Los comentarios aparecen en el chatter del lugar asociado.

---

## Constraints

### Nivel máximo de respuestas
```python
@api.constrains('parent_id')
def _check_nivel_respuestas(self):
    # Solo permite 1 nivel de anidamiento
    # Respuesta a respuesta = Error
```

---

## SQL Schema

```sql
-- Tabla principal de comentarios
CREATE TABLE memoria_viva_comentario (
    id SERIAL PRIMARY KEY,
    lugar_id INTEGER REFERENCES memoria_viva_historia(id),
    parent_id INTEGER REFERENCES memoria_viva_comentario(id),
    autor_id INTEGER REFERENCES res_users(id),
    contenido TEXT NOT NULL,
    estado VARCHAR DEFAULT 'pendiente',
    contiene_palabras_prohibidas BOOLEAN DEFAULT FALSE,
    fecha_moderacion TIMESTAMP,
    moderado_por INTEGER REFERENCES res_users(id),
    create_uid INTEGER REFERENCES res_users(id),
    write_uid INTEGER REFERENCES res_users(id),
    create_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    write_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tabla de palabras prohibidas
CREATE TABLE memoria_viva_palabra_prohibida (
    id SERIAL PRIMARY KEY,
    name VARCHAR NOT NULL,
    active BOOLEAN DEFAULT TRUE,
    settings_id INTEGER REFERENCES memoria_viva_settings(id)
);
```
