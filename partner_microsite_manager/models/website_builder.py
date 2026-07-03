#!/usr/bin/env python3
"""Helper puro para generar el HTML de los microsites.
Reutilizado por res.partner y por scripts de importación externa.
"""

import json
import re
from datetime import datetime

from markupsafe import escape

CTA_IMAGE_ID = 20891
SUBVENCIONES_IMAGE_ID = 16549

# Todo valor de usuario interpolado en el HTML acaba dentro del arch QWeb de
# la vista homepage: sin escapar, un campo con '<', '&' o directivas t-*
# rompe el XML del arch o, peor, se compila y ejecuta como QWeb para todos
# los visitantes del microsite. escape() (markupsafe) neutraliza ambas cosas.


def _safe_map_url(url):
    """Solo URLs http(s) pueden ir al src del iframe del mapa."""
    url = str(url or '').strip()
    if url.startswith(('http://', 'https://')):
        return url
    return ''


def build_hero_section(nombre_empresa, hero_image_id=None, button_text='Tienda'):
    titulo = escape(nombre_empresa or '')
    button_text = escape(button_text or 'Tienda')
    if hero_image_id:
        bg_style = f"background-image: url('/web/image/ir.attachment/{int(hero_image_id)}/datas'); background-size: cover; background-position: center; background-attachment: fixed;"
    else:
        bg_style = "background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);"
    return f'''<section class="s_cover parallax s_parallax_is_fixed bg-black-50 pt96 pb96" data-snippet="s_cover" data-name="Hero" style="{bg_style} min-height: 60vh; display: flex; align-items: center; position: relative;">
    <div style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.4); z-index: 0;"></div>
    <div class="s_allow_columns container" style="position: relative; z-index: 1;">
        <h1 class="display-1" style="text-align: center; color: white; text-shadow: 2px 2px 4px rgba(0,0,0,0.7);">
            <span class="display-4-fs">{titulo}</span>
        </h1>
        <p style="text-align: center;">
            <a class="btn btn-lg btn-primary o_translate_inline" href="/shop">{button_text}</a>
        </p>
    </div>
</section>'''


def parse_horario_to_json(horario_str):
    """Parsea horario del formato CSV a JSON estructurado, soportando descansos.
    Ejemplo: 'L-V 10:00-13:30/L-V 16:30-20:00/S 10:00-14:00'
    Devuelve un dict donde cada día puede tener un string (1 franja) o una lista (2 franjas).
    """
    if not horario_str:
        return {}
    horario_str = str(horario_str).strip()
    if not horario_str or horario_str.lower() in ['nan', 'none', '']:
        return {}
    dias_map = {'L': 'Lunes', 'M': 'Martes', 'X': 'Miércoles',
                'J': 'Jueves', 'V': 'Viernes', 'S': 'Sábado', 'D': 'Domingo'}
    result = {}
    try:
        bloques = re.split(r'\s*/\s*|\s*·\s*', horario_str)
        for bloque in bloques:
            bloque = bloque.strip()
            match = re.match(r'([LMXJVSD,\-]+)\s+(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})', bloque)
            if match:
                dias_str, hora_ini, hora_fin = match.groups()
                horario = f"{hora_ini} - {hora_fin}"
                dias_lista = []
                if '-' in dias_str and ',' not in dias_str:
                    partes = dias_str.split('-')
                    claves = list(dias_map.keys())
                    if len(partes) == 2 and partes[0] in claves and partes[1] in claves:
                        idx_ini = claves.index(partes[0])
                        idx_fin = claves.index(partes[1])
                        dias_lista = [claves[i] for i in range(idx_ini, idx_fin + 1)]
                    else:
                        # Lista de días separados por guion (ej. L-M-X-J-V-S)
                        dias_lista = [d for d in partes if d in dias_map]
                else:
                    dias_lista = [d.strip() for d in dias_str.split(',')]
                for d in dias_lista:
                    if d in dias_map:
                        dia_nombre = dias_map[d]
                        result.setdefault(dia_nombre, [])
                        result[dia_nombre].append(horario)
        # Normalizar: si un día solo tiene 1 franja, guardar como string; si 2, mantener lista
        for dia in list(result.keys()):
            if len(result[dia]) == 1:
                result[dia] = result[dia][0]
    except Exception:
        pass
    return result


def build_horario_accordion(horario_str, subdomain):
    dias_json = parse_horario_to_json(horario_str)
    subdomain = escape(subdomain or '')
    if not dias_json:
        return f'<small class="text-muted text-center d-block">{escape(horario_str)}</small>'
    dias_semana = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
    hoy = dias_semana[datetime.now().weekday()]
    hora_hoy_raw = dias_json.get(hoy, 'Cerrado')

    def _format_horario(val):
        if isinstance(val, list):
            return ' / '.join(val)
        return val

    hora_hoy_str = _format_horario(hora_hoy_raw)
    dias_html = []
    for dia in dias_semana:
        if dia in dias_json:
            hora = _format_horario(dias_json[dia])
            bold = 'fw-bold' if dia == hoy else ''
            dias_html.append(f'<div class="{bold}" style="display: flex; justify-content: space-between; padding: 2px 0;"><span>{dia}</span><span>{hora}</span></div>')
    dias_html_str = '\n'.join(dias_html)

    # Inyectar JSON de horarios para que el navegador calcule dinámicamente el estado
    horarios_js = {}
    for dia in dias_semana:
        if dia in dias_json:
            val = dias_json[dia]
            franjas = val if isinstance(val, list) else [val]
            horarios_js[dia] = [f.split(' - ') for f in franjas]
        else:
            horarios_js[dia] = []

    return f'''<div class="horario-card-accordion mt-3" style="text-align: left;">
    <div class="accordion accordion-flush" id="horarioCardAccordion_{subdomain}">
        <div class="accordion-item" style="border: 1px solid #dee2e6; border-radius: 8px; overflow: hidden;">
            <h2 class="accordion-header" style="margin: 0;">
                <button class="accordion-button collapsed py-2 px-3" type="button" data-bs-toggle="collapse" data-bs-target="#flushHorario_{subdomain}" style="background: #f8f9fa; font-size: 0.9rem; font-weight: 500;">
                    <span style="font-weight: 600;"><span id="horario-dia-{subdomain}">{hoy}</span>: <span id="horario-hora-{subdomain}">{hora_hoy_str}</span></span>
                    <span class="ms-auto" style="font-size: 0.8rem; font-family: monospace;" id="horario-estado-{subdomain}">...</span>
                </button>
            </h2>
            <div id="flushHorario_{subdomain}" class="accordion-collapse collapse" data-bs-parent="#horarioCardAccordion_{subdomain}">
                <div class="accordion-body p-2" style="background: #fff;">
                    <div class="horario-semana-list">
                        {dias_html_str}
                    </div>
                </div>
            </div>
        </div>
    </div>
    <script>
        //<![CDATA[
        (function(){{
            var horarios = {json.dumps(horarios_js)};
            var dias = ['Lunes','Martes','Miércoles','Jueves','Viernes','Sábado','Domingo'];
            var now = new Date();
            var canariasOffset = 0; // UTC+0 en invierno, UTC+1 en verano se maneja automáticamente por la zona
            var canariasTime = new Date(now.toLocaleString('en-US', {{timeZone: 'Atlantic/Canary'}}));
            var diaIdx = canariasTime.getDay();
            if (diaIdx === 0) diaIdx = 7; // Domingo -> índice 7 para ajustar a Lunes=0... pero JS getDay() ya tiene Domingo=0
            // Reajuste: getDay() devuelve 0=Domingo, 1=Lunes... así que:
            var diaNombre = dias[(diaIdx === 0 ? 6 : diaIdx - 1)];
            var hh = String(canariasTime.getHours()).padStart(2, '0');
            var mm = String(canariasTime.getMinutes()).padStart(2, '0');
            var hm = hh + ':' + mm;
            var franjas = horarios[diaNombre] || [];
            var abierto = false;
            for (var i = 0; i < franjas.length; i++){{
                if (hm >= franjas[i][0] && hm <= franjas[i][1]){{
                    abierto = true;
                    break;
                }}
            }}
            var estadoSpan = document.getElementById('horario-estado-{subdomain}');
            if (estadoSpan){{
                estadoSpan.textContent = abierto ? 'Abierto ahora' : 'Cerrado';
                estadoSpan.style.color = abierto ? '#28a745' : '#dc3545';
            }}
            var diaSpan = document.getElementById('horario-dia-{subdomain}');
            if (diaSpan){{ diaSpan.textContent = diaNombre; }}
            var horaSpan = document.getElementById('horario-hora-{subdomain}');
            if (horaSpan){{ horaSpan.textContent = {json.dumps(str(hora_hoy_str))}.replace(/__DIA__/g, diaNombre); }}
        }})();
        //]]>
    </script>
</div>'''


def build_features_section(horario, entrega, parking, subdomain):
    items_html = ''
    entrega = escape(entrega) if entrega else entrega
    parking = escape(parking) if parking else parking
    if horario and str(horario).strip() and str(horario).lower() not in ['nan', 'none', '']:
        horario_html = build_horario_accordion(horario, subdomain)
        items_html += f'''<div class="col-lg-4 pt16 pb16 text-center">
            <span class="fa fa-clock-o fa-2x mb-3" style="display: block; color: var(--o-color-1);"></span>
            <h5 class="fw-bold">Horario</h5>
            {horario_html}
        </div>'''
    if parking and str(parking).strip() and str(parking).lower() not in ['nan', 'none', '']:
        items_html += f'''<div class="col-lg-4 pt16 pb16 text-center">
            <span class="fa fa-map-marker fa-2x mb-3" style="display: block; color: var(--o-color-1);"></span>
            <h5 class="fw-bold">Parking</h5>
            <p class="text-muted">{parking}</p>
        </div>'''
    if entrega and str(entrega).strip() and str(entrega).lower() not in ['nan', 'none', '']:
        items_html += f'''<div class="col-lg-4 pt16 pb16 text-center">
            <span class="fa fa-truck fa-2x mb-3" style="display: block; color: var(--o-color-1);"></span>
            <h5 class="fw-bold">Entrega / Envío</h5>
            <p class="text-muted">{entrega}</p>
        </div>'''
    if not items_html:
        return ''
    return f'''<section class="s_features pt48 pb48" data-snippet="s_features" data-name="Horario">
    <div class="container">
        <div class="row justify-content-center">
            {items_html}
        </div>
    </div>
</section>'''


def build_acerca_section(sec1_texto, sec2_texto, sec1_titulo, sec2_titulo, subdomain):
    items = []
    subdomain = escape(subdomain or '')
    if sec1_texto and str(sec1_texto).strip() and str(sec1_texto).lower() not in ['nan', 'none', '']:
        titulo = sec1_titulo if sec1_titulo and str(sec1_titulo).lower() not in ['nan', 'none', ''] else 'Sobre nosotros'
        preview = str(sec1_texto)[:120] + '...' if len(str(sec1_texto)) > 120 else str(sec1_texto)
        items.append({'titulo': titulo, 'preview': preview, 'texto': str(sec1_texto), 'icono': 'fa-book', 'id': f'acerca1_{subdomain}'})
    if sec2_texto and str(sec2_texto).strip() and str(sec2_texto).lower() not in ['nan', 'none', '']:
        titulo = sec2_titulo if sec2_titulo and str(sec2_titulo).lower() not in ['nan', 'none', ''] else 'Nuestros servicios'
        preview = str(sec2_texto)[:120] + '...' if len(str(sec2_texto)) > 120 else str(sec2_texto)
        items.append({'titulo': titulo, 'preview': preview, 'texto': str(sec2_texto), 'icono': 'fa-cogs', 'id': f'acerca2_{subdomain}'})
    if not items:
        return ''
    cols_html = ''
    for item in items:
        col_html = f'''<div class="border o_colored_level col-lg-6 text-center pt-4 pb-4" data-name="Column">
            <span class="fa {item['icono']} fa-3x mb-3" style="display: block;"></span>
            <h6 class="text-center">{escape(item['titulo'])}</h6>
            <small class="text-muted d-block" style="padding: 0 20px;">{escape(item['preview'])}</small>
            <div class="mt-3 text-center">
                <a href="#{item['id']}" data-bs-toggle="collapse" class="btn btn-primary rounded-pill px-4">Leer más</a>
            </div>
            <div id="{item['id']}" class="collapse mt-3">
                <div class="card card-body bg-light">{escape(item['texto'])}</div>
            </div>
        </div>'''
        cols_html += col_html
    return f'''<section class="s_attributes_vertical o_colored_level pt48 pb56" data-snippet="s_attributes_vertical" data-name="Acerca">
    <div class="container">
        <div class="row justify-content-center">
            {cols_html}
        </div>
    </div>
</section>'''


def build_cta_section():
    return f'''<section class="s_text_image pt80 pb80 o_colored_level" data-snippet="s_text_image" data-name="Zona Comercial">
    <div class="container">
        <div class="row o_grid_mode" data-row-count="13">
            <div class="o_colored_level o_grid_item g-col-lg-6 g-height-13 col-lg-6 o_grid_item_image" style="grid-area: 1 / 7 / 14 / 13; z-index: 2;">
                <img src="/web/image/{CTA_IMAGE_ID}/showcase_bg_aeropatin.jpg" class="img img-fluid mx-auto rounded" alt="" loading="lazy"/>
            </div>
            <div class="o_colored_level o_grid_item g-col-lg-5 g-height-7 col-lg-5" style="z-index: 1; grid-area: 5 / 2 / 12 / 7;">
                <h2 class="h3-fs"><strong>CIENTOS DE COMERCIOS EN TU ZONA</strong></h2>
                <div><strong>¡Increíbles ofertas por descubrir!<br/><br/></strong></div>
                <div>Atrévete a explorar nuestras Zonas Comerciales Abiertas. En un solo clic, descubrirás una amplia variedad de comercios, miles de productos irresistibles y oportunidades exclusivas. ¡Tu próxima experiencia de compra te espera aquí!<br/><br/></div>
                <p><a href="https://canariasconectada.es/directorio" class="btn btn-secondary btn-lg" style="color: #fff !important; text-decoration: none;">Directorio</a></p>
            </div>
        </div>
    </div>
</section>'''


def build_formulario_section(subdomain, map_url, company_info, website_url='', phone2=''):
    direccion = ''
    telefono = ''
    email = ''
    if company_info:
        if company_info.get('address'):
            direccion = str(company_info['address'])
        else:
            parts = []
            if company_info.get('street'):
                parts.append(str(company_info['street']).replace('&nbsp;', ' '))
            if company_info.get('city'):
                parts.append(str(company_info['city']))
            if company_info.get('zip'):
                parts.append(str(company_info['zip']))
            direccion = ', '.join(parts)
        if company_info.get('phone'):
            telefono = str(company_info['phone'])
        if company_info.get('email'):
            email = str(company_info['email'])
    contacto_html = ''
    if direccion:
        contacto_html += f'<p class="mb-2"><i class="fa fa-map-marker fa-fw mr-2 text-primary"/>{escape(direccion)}</p>\n'
    if telefono:
        contacto_html += f'<p class="mb-2"><i class="fa fa-phone fa-fw mr-2 text-primary"/>{escape(telefono)}</p>\n'
    if phone2:
        contacto_html += f'<p class="mb-2"><i class="fa fa-phone fa-fw mr-2 text-primary"/>{escape(phone2)}</p>\n'
    if email:
        contacto_html += f'<p class="mb-2"><i class="fa fa-envelope fa-fw mr-2 text-primary"/>{escape(email)}</p>\n'
    if website_url:
        url_display = str(website_url)
        if not url_display.startswith(('http://', 'https://')):
            url_display = 'https://' + url_display
        contacto_html += f'<p class="mb-2"><i class="fa fa-globe fa-fw mr-2 text-primary"/><a href="{escape(url_display)}" target="_blank">{escape(website_url)}</a></p>\n'
    return f'''<section class="s_website_form pt48 pb48" data-snippet="s_website_form" data-name="Formulario">
    <div class="container">
        <div class="row">
            <div class="col-lg-6 pb16">
                <section class="s_text_block" data-snippet="s_text_block">
                    <h4 class="mb-3"><span class="fa fa-envelope" style="margin-right: 8px;"></span><strong>ESCRÍBENOS</strong></h4>
                    <form action="/website/form/" method="post" enctype="multipart/form-data" class="s_website_form form-horizontal" data-model_name="crm.lead" data-success_page="/contactus-thank-you">
                        <div class="row s_col_no_resize s_col_no_bg">
                            <div class="mb-0 py-2 col-12 s_website_form_field s_website_form_custom">
                                <label class="s_website_form_label"><span class="s_website_form_label_content">Nombre</span><span class="s_website_form_mark"> *</span></label>
                                <input type="text" class="form-control s_website_form_input" name="contact_name" required=""/>
                            </div>
                            <div class="mb-0 py-2 col-12 s_website_form_field s_website_form_custom">
                                <label class="s_website_form_label"><span class="s_website_form_label_content">Email</span><span class="s_website_form_mark"> *</span></label>
                                <input type="email" class="form-control s_website_form_input" name="email_from" required=""/>
                            </div>
                            <div class="mb-0 py-2 col-12 s_website_form_field s_website_form_custom">
                                <label class="s_website_form_label"><span class="s_website_form_label_content">Teléfono</span></label>
                                <input type="tel" class="form-control s_website_form_input" name="phone"/>
                            </div>
                            <div class="mb-0 py-2 col-12 s_website_form_field s_website_form_custom">
                                <label class="s_website_form_label"><span class="s_website_form_label_content">Mensaje</span><span class="s_website_form_mark"> *</span></label>
                                <textarea class="form-control s_website_form_input" name="description" rows="3" required=""></textarea>
                            </div>
                            <div class="mb-0 py-1 col-12 s_website_form_submit">
                                <button type="submit" class="btn btn-primary btn-lg w-100 s_website_form_send">Enviar</button>
                            </div>
                        </div>
                    </form>
                </section>
            </div>
            <div class="col-lg-6">
                <div class="mt-3 mb-3">
                    <iframe src="{escape(_safe_map_url(map_url))}" width="100%" height="200" style="border:0; border-radius: 8px;"></iframe>
                </div>
                <h4 class="mb-3"><span class="fa fa-map-marker" style="margin-right: 8px;"></span><strong>ENCUÉNTRANOS</strong></h4>
                {contacto_html}
            </div>
        </div>
    </div>
</section>'''


def build_subvenciones_section():
    return f'''<section class="s_picture pt64 pb64 o_colored_level" data-snippet="s_picture" data-name="Subvenciones">
    <div class="container">
        <div class="row justify-content-center">
            <div class="o_colored_level col-lg-12 text-center">
                <figure class="figure w-100">
                    <img src="/web/image/{SUBVENCIONES_IMAGE_ID}/subvenciones.png" class="figure-img img-fluid rounded" alt="Subvenciones" loading="lazy" style="max-height: 120px;"/>
                </figure>
            </div>
        </div>
    </div>
</section>'''


def build_social_link(url, icon_class, label):
    if url and str(url).strip() and str(url).lower() not in ['nan', 'none', '', 'false']:
        return f'<a href="{escape(url)}" target="_blank" class="text-white fs-4" title="{escape(label)}"><i class="fa {icon_class}"></i></a>'
    return ''


def build_footer(nombre_comercial, rrss=None):
    nombre_display = escape(nombre_comercial) if nombre_comercial else ''
    rrss = rrss or {}
    social_icons = []
    social_links = [
        ('facebook', 'fa-facebook', 'Facebook'),
        ('instagram', 'fa-instagram', 'Instagram'),
        ('twitter', 'fa-twitter', 'Twitter'),
        ('linkedin', 'fa-linkedin', 'LinkedIn'),
        ('youtube', 'fa-youtube-play', 'YouTube'),
    ]
    for key, icon, label in social_links:
        link = build_social_link(rrss.get(key), icon, label)
        if link:
            social_icons.append(link)
    social_html = '\n                    '.join(social_icons) if social_icons else ''
    badges_html = '''<div class="d-flex justify-content-center gap-2 flex-wrap mb-3">
                    <a href="https://canariasconectada.es/silver-economy" target="_blank" class="btn btn-sm" style="background: rgba(192, 192, 192, 0.2); border: 1px solid rgb(192, 192, 192); color: white !important;">
                        <i class="fa fa-users me-1"/> Comercio Silver Economy
                    </a>
                    <a href="https://canariasconectada.es/sostenible" target="_blank" class="btn btn-sm" style="background: rgba(40, 167, 69, 0.2); border: 1px solid rgb(40, 167, 69); color: white !important;">
                        <i class="fa fa-leaf me-1"/> Comercio Sostenible
                    </a>
                </div>'''
    return f'''<footer class="o_footer bg-black text-light py-4" data-name="Footer">
    <div class="container">
        <div class="row justify-content-center mb-3">
            <div class="col-auto d-flex gap-3 align-items-center">
                {social_html}
            </div>
        </div>
        <div class="row justify-content-center text-center mb-3">
            <div class="col-lg-10">
                <h5 class="fw-bold mb-3" style="color: white !important;">{nombre_display}</h5>
                {badges_html}
                <p class="mb-3 mt-3">© 2025 Todos los derechos reservados</p>
                <p class="small mb-3">
                    <i class="fa fa-shield me-1"/>
                    <a href="/politica-privacidad" class="link-light text-decoration-none">Política de privacidad</a>
                    <span class="mx-2">·</span>
                    <a href="/terminos-condiciones" class="link-light text-decoration-none">Términos y condiciones</a>
                    <span class="mx-2">·</span>
                    <a href="/politica-cookies" class="link-light text-decoration-none">Política de Cookies</a>
                </p>
            </div>
        </div>
    </div>
</footer>'''
