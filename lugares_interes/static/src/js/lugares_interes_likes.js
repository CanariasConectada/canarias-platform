odoo.define('lugares_interes.likes', function (require) {
    'use strict';
    
    $(document).ready(function () {
        $('.like-btn').on('click', function (e) {
            e.stopPropagation();
            e.preventDefault();
            var lugarId = $(this).data('lugar-id');
            var $btn = $(this);
            
            $.ajax({
                url: '/lugares-de-interes/like/' + lugarId,
                type: 'POST',
                contentType: 'application/json',
                success: function (data) {
                    var $icon = $btn.find('i');
                    if (data.success) {
                        $icon.removeClass('fa-heart-o').addClass('fa-heart');
                        var $counter = $btn.closest('.card').find('.card-body .fa-heart.text-danger').parent().find('span, .like-count');
                        if ($counter.length) {
                            $counter.text(data.like_count);
                        }
                    } else if (data.already_liked) {
                        $icon.removeClass('fa-heart-o').addClass('fa-heart');
                    }
                },
                error: function () {
                    console.error('Error dando like');
                }
            });
        });
    });
});
