from . import models


def post_init_hook(env):
    """Sincroniza menús de todos los websites tras instalar el módulo."""
    env['website.menu']._sync_all_website_menus()
