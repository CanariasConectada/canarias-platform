# Guía de Estilos - Frontend

## Clases CSS Utilizadas

### Contenedor Principal
```html
<div class="row mt-5">  <!-- Sección de comentarios -->
  <div class="col-12">
```

### Tarjeta de Comentario
```html
<div class="card border-0 shadow-sm mb-3">
  <div class="card-body">
```

### Avatar
```html
<img class="rounded-circle me-3 bg-light" 
     style="width: 50px; height: 50px; object-fit: cover;"
     src="...">
```

### Nombre del Autor
```html
<h6 class="mb-1 fw-bold">Nombre</h6>
```

### Fecha
```html
<small class="text-muted">06/04/2026 20:56</small>
```

### Contenido
```html
<p class="mb-2">Contenido del comentario...</p>
```

### Botón Responder
```html
<button class="btn btn-sm btn-link p-0 text-decoration-none">
  <i class="fa fa-reply me-1"></i>Responder
</button>
```

---

## Estructura HTML

```html
<!-- Sección de Comentarios -->
<div class="row mt-5">
  <div class="col-12">
    
    <!-- Header -->
    <h3 class="mb-4">
      <i class="fa fa-comments me-2 text-primary"></i>
      Comentarios
      <span class="badge bg-secondary" id="total-comentarios">0</span>
    </h3>
    
    <!-- Formulario (solo usuarios logueados) -->
    <div class="card border-0 shadow-sm mb-4">
      <div class="card-body">
        <h5 class="mb-3">Deja tu comentario</h5>
        <form id="comentarioForm">
          <textarea class="form-control" rows="3"></textarea>
          <button type="submit" class="btn btn-primary">
            <i class="fa fa-paper-plane me-2"></i>Enviar
          </button>
        </form>
      </div>
    </div>
    
    <!-- Mensaje para anónimos -->
    <div class="alert alert-info">
      <a href="/web/login">Inicia sesión</a> para dejar un comentario.
    </div>
    
    <!-- Lista de Comentarios -->
    <div id="comentarios-lista"></div>
    
    <!-- Botón Ver Más -->
    <button id="verMasComentarios" class="btn btn-outline-primary d-none">
      <i class="fa fa-chevron-down me-2"></i>Ver más comentarios
    </button>
    
  </div>
</div>
```

---

## Colores Bootstrap

| Elemento | Clase | Color |
|----------|-------|-------|
| Icono de comentarios | `text-primary` | Azul |
| Badge de contador | `bg-secondary` | Gris |
| Botón enviar | `btn-primary` | Azul |
| Botón ver más | `btn-outline-primary` | Azul outline |
| Alerta login | `alert-info` | Azul claro |
| Card comentario | `shadow-sm` | Sombra suave |
| Borde izquierdo respuestas | `border-primary` | Azul |

---

## Espaciados

| Elemento | Espaciado |
|----------|-----------|
| Sección comentarios | `mt-5` (margin-top: 3rem) |
| Entre comentarios | `mb-3` (margin-bottom: 1rem) |
| Dentro de card | `p-3` (padding: 1rem) |
| Avatar | `me-3` (margin-right: 1rem) |
| Respuestas indent | `ms-4` (margin-left: 1.5rem) |

---

## Responsive

La sección de comentarios usa el sistema de grid de Bootstrap:

```html
<div class="row">
  <div class="col-12">  <!-- Ocupa todo el ancho en todos los dispositivos -->
```

---

## Mejoras Sugeridas

### 1. Animaciones
```css
/* Suavizar aparición de comentarios */
.comentario-nuevo {
  animation: fadeIn 0.3s ease-in;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(-10px); }
  to { opacity: 1; transform: translateY(0); }
}
```

### 2. Estados de Comentario
```css
/* Comentario pendiente de moderación */
.comentario-pendiente {
  border-left: 3px solid #ffc107;
  background-color: #fffbf0;
}

/* Comentario propio */
.comentario-propio {
  border-left: 3px solid #28a745;
}
```

### 3. Hover Effects
```css
/* Resaltar comentario al pasar el mouse */
.card-comentario:hover {
  box-shadow: 0 0.5rem 1rem rgba(0,0,0,0.15);
  transition: box-shadow 0.2s ease;
}
```

---

## Archivos Relacionados

- `static/src/js/memoria_viva_comments.js` - JavaScript
- `views/memoria_viva_templates.xml` - Templates QWeb
- `static/src/css/memoria_viva.scss` - Estilos SCSS
