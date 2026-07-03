# Sustainability Certification

**Versión:** 19.0.2.0.0 | **Licencia:** AGPL-3 | **Autor:** Canarias Conectada

Evaluación y certificación de Sostenibilidad para las empresas del
marketplace de Canarias Conectada, construida sobre la app `survey`. Un
cuestionario de 40 preguntas otorga sellos Bronce/Plata/Oro que se muestran
en el backend, en el directorio público y en el microsite de la empresa, con
caducidad, plazos de reintento y recordatorios por correo.

Convive con su módulo gemelo `silver_economy`: la lógica compartida sobre
`survey.user_input` usa el hook cooperativo
`survey.survey._get_certification_config()` para que cada tipo de encuesta
se puntúe siempre con los umbrales de su propio módulo.

La documentación detallada está en los fragmentos de [`readme/`](readme/):
[descripción](readme/DESCRIPTION.md) · [configuración](readme/CONFIGURE.md) ·
[uso](readme/USAGE.md) · [historial de cambios](readme/HISTORY.md) ·
[contribuidores](readme/CONTRIBUTORS.md)

## Dependencias

- `survey`, `website` (Odoo core)
- `website_directory` (canarias-platform)

## Licencia

[AGPL-3](https://www.gnu.org/licenses/agpl-3.0.html)
