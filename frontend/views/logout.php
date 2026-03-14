<?php
use Frontend\App\Auth\Session;

Session::init();
Session::destroy();

header('Location: /login');
exit;
