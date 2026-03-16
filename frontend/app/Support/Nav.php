<?php
namespace Frontend\App\Support;

class Nav
{
    public static function items(): array
    {
        return [
            [
                'key' => 'dashboard',
                'label' => 'Trung tâm',
                'href' => '/',
                'section' => 'admin',
            ],
            [
                'key' => 'cameras',
                'label' => 'Camera',
                'href' => '/cameras',
                'section' => 'admin',
            ],
            [
                'key' => 'violations',
                'label' => 'Vi phạm',
                'href' => '/violations',
                'section' => 'admin',
            ],
        ];
    }
}
