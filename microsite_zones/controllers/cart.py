# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
from odoo import http
from odoo.http import request
from odoo.exceptions import UserError
from odoo.addons.website_sale.controllers.cart import Cart

_logger = logging.getLogger(__name__)


class CartZones(Cart):
    """
    Controlador que extiende WebsiteSaleCartController para aplicar
    sudo() al acceder a variantes de producto en zonas/Canarias.
    
    Esto soluciona el problema de acceso para usuarios públicos cuando
    multicompany_isolation restringe product.product a company_ids del usuario.
    """

    @http.route(
        route='/shop/cart/add',
        type='jsonrpc',
        auth='public',
        methods=['POST'],
        website=True,
        sitemap=False
    )
    def add_to_cart(
        self,
        product_template_id,
        product_id,
        quantity=1.0,
        uom_id=None,
        product_custom_attribute_values=None,
        no_variant_attribute_value_ids=None,
        linked_products=None,
        **kwargs
    ):
        """
        Sobrescribe para usar sudo() cuando estamos en una zona o Canarias Conectada.
        """
        website = request.website
        
        # Si estamos en zona o Canarias Conectada, usar sudo() para acceder al producto
        if (website.zone_id or website.is_canarias_conectada) and product_id:
            _logger.debug(f"[ZONES CART] Usando sudo para add_to_cart en {website.name}, product_id: {product_id}")
            
            order_sudo = request.cart or request.website._create_cart()
            quantity = int(quantity)

            # Usar sudo() para evitar restricciones de multicompany_isolation
            product = request.env['product.product'].sudo().browse(product_id).exists()
            if not product or not product._is_add_to_cart_allowed():
                raise UserError(_(
                    "The given product does not exist therefore it cannot be added to cart."
                ))

            added_qty_per_line = {}
            values = order_sudo.with_context(skip_cart_verification=True)._cart_add(
                product_id=product_id,
                quantity=quantity,
                uom_id=uom_id,
                product_custom_attribute_values=product_custom_attribute_values,
                no_variant_attribute_value_ids=no_variant_attribute_value_ids,
                **kwargs,
            )
            line_ids = {product_template_id: values['line_id']}
            added_qty_per_line[values['line_id']] = values['added_qty']
            is_combo = product.type == 'combo'
            updated_line = (
                values['line_id']
                and order_sudo.order_line.filtered(lambda line: line.id == values['line_id'])
            ) or order_sudo.env['sale.order.line']

            if linked_products and values['line_id']:
                for product_data in linked_products:
                    product_sudo = request.env['product.product'].sudo().browse(
                        product_data['product_id']
                    ).exists()
                    if product_data['quantity'] and (
                        not product_sudo
                        or (
                            not product_sudo._is_add_to_cart_allowed()
                            and not product_data.get('combo_item_id')
                        )
                    ):
                        raise UserError(_(
                            "The given product does not exist therefore it cannot be added to cart."
                        ))

                    product_values = order_sudo.with_context(skip_cart_verification=True)._cart_add(
                        product_id=product_data['product_id'],
                        quantity=product_data['quantity'],
                        uom_id=product_data.get('uom_id'),
                        product_custom_attribute_values=product_data['product_custom_attribute_values'],
                        no_variant_attribute_value_ids=[
                            int(value_id) for value_id in product_data['no_variant_attribute_value_ids']
                        ],
                        linked_line_id=line_ids[product_data['parent_product_template_id']],
                        **self._get_additional_cart_update_values(product_data),
                        **kwargs,
                    )
                    if is_combo and not product_values.get('quantity'):
                        updated_line.unlink()
                        return {
                            'cart_quantity': order_sudo.cart_quantity,
                            'notification_info': {
                                'warning': product_values.get('warning', ''),
                            },
                            'added_qty_per_line': added_qty_per_line,
                        }
                    line_ids[product_data['product_template_id']] = product_values['line_id']
                    added_qty_per_line[product_values['line_id']] = product_values['added_qty']

            # Llamar al método que genera la notificación del carrito
            return self._get_cart_notification_and_values(
                order_sudo,
                line_ids,
                added_qty_per_line,
                updated_line,
                kwargs,
            )
        
        # Comportamiento normal para microsites individuales
        return super().add_to_cart(
            product_template_id=product_template_id,
            product_id=product_id,
            quantity=quantity,
            uom_id=uom_id,
            product_custom_attribute_values=product_custom_attribute_values,
            no_variant_attribute_value_ids=no_variant_attribute_value_ids,
            linked_products=linked_products,
            **kwargs
        )
