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
                'href' => '/index.php',
                'section' => 'admin',
            ],
            [
                'key' => 'cameras',
                'label' => 'Camera',
                'href' => '/cameras.php',
                'section' => 'admin',
            ],
            [
                'key' => 'violations',
                'label' => 'Vi phạm',
                'href' => '/violations.php',
                'section' => 'admin',
            ],
        ];
    }
}
