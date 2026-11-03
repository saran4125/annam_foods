<?php
declare(strict_types=1);
namespace Annam;
/** A private, single-use owner setup for the bundled local-database release. */
final class Installation {
    public static function file():string{return ANNAM_ROOT.'/storage/installation.json';}
    public static function config():?array{return is_file(self::file())?json_decode(file_get_contents(self::file()),true,32,JSON_THROW_ON_ERROR):null;}
    public static function load():void {
        $config=self::config();if(!$config)return;@chmod(self::file(),0600);if(is_file(ANNAM_ROOT.'/storage/annam.sqlite'))@chmod(ANNAM_ROOT.'/storage/annam.sqlite',0600);
        foreach(['APP_SECRET','SECRETS_KEY','APP_URL','APP_ENV','STORE_SLUG','PAYMENTS_ENABLED','MESSAGING_ENABLED','REQUIRE_CRON'] as $key)if(isset($config[$key])&&getenv($key)===false)putenv($key.'='.$config[$key]);
        if(getenv('DATABASE_DSN')===false)putenv('DATABASE_DSN=sqlite:'.ANNAM_ROOT.'/storage/annam.sqlite');
        if(getenv('MEDIA_ROOT')===false)putenv('MEDIA_ROOT='.dirname(ANNAM_ROOT).'/public_html/media');
        foreach(['sessions','logs','backups','bills'] as $folder)if(!is_dir(ANNAM_ROOT.'/storage/'.$folder))mkdir(ANNAM_ROOT.'/storage/'.$folder,0700,true);
    }
    public static function pending():bool{$config=self::config();return $config!==null&&!($config['complete']??false);}
    public static function save(array $config):void {
        $tmp=self::file().'.'.bin2hex(random_bytes(8));if(file_put_contents($tmp,json_encode($config,JSON_PRETTY_PRINT|JSON_THROW_ON_ERROR),LOCK_EX)===false)throw new \RuntimeException('Private setup settings could not be saved.');chmod($tmp,0600);if(!rename($tmp,self::file()))throw new \RuntimeException('Could not activate the private configuration.');
    }
    public static function handle():void {
        $missing=[];foreach(['pdo_sqlite','curl','mbstring','fileinfo','openssl','zip'] as $extension)if(!extension_loaded($extension))$missing[]=$extension;if($missing)throw new HttpError(503,'Enable these PHP extensions in Hostinger: '.implode(', ',$missing).'. No cloud database is needed.');
        $path=parse_url($_SERVER['REQUEST_URI'],PHP_URL_PATH);if($path!=='/setup/')redirect('/setup/');$method=$_SERVER['REQUEST_METHOD'];if(!in_array($method,['GET','POST'],true))throw new HttpError(405,'GET or POST required.');
        $https=(!empty($_SERVER['HTTPS'])&&strtolower((string)$_SERVER['HTTPS'])!=='off')||($_SERVER['SERVER_PORT']??'')==='443';if(getenv('APP_ENV')==='production'&&!$https)throw new HttpError(403,'Open your website using HTTPS to complete private setup.');
        $host=$_SERVER['HTTP_HOST']??'';if(!preg_match('/^[a-z0-9.:-]+$/iD',$host))throw new HttpError(400,'Invalid website address.');$url=($https?'https://':'http://').$host;if(!getenv('APP_URL'))putenv('APP_URL='.$url);Security::start();$error='';
        if($method==='POST'){
            Security::verifyCsrf();$store=new Store(new Database());Operations::limit($store,'first-setup:'.($_SERVER['REMOTE_ADDR']??''),10,900);$config=self::config();
            if(!hash_equals($config['setup_token_hash'],hash('sha256',(string)($_POST['setup_code']??''))))$error='Enter the private setup code from SETUP-ACCESS.txt in your ZIP.';
            else{
                $username=trim((string)($_POST['username']??''));$password=(string)($_POST['password']??'');
                $hasAccounts=(bool)$store->db->one('SELECT id FROM auth_user LIMIT 1');$validName=$hasAccounts?($username!==''&&mb_strlen($username)<=150):(bool)preg_match('/^[a-zA-Z0-9_.-]{3,100}$/D',$username);
                if(!$validName||strlen($password)<($hasAccounts?1:12)||strlen($password)>($hasAccounts?1024:128)||$password!==($_POST['password_confirm']??''))$error='Use a username of 3–100 letters/numbers and matching passwords of 12–128 characters.';
                else{
                    // Serialize the DB and configuration activation under a private filesystem lock.
                    $lock=fopen(ANNAM_ROOT.'/storage/setup.lock','c');if(!$lock||!flock($lock,LOCK_EX))throw new \RuntimeException('Setup is busy.');
                    try{$config=self::config();if($config['complete']??false)redirect('/manage/login/');$store->db->transaction(function()use($store,$username,$password){
                        if($store->db->one('SELECT id FROM auth_user LIMIT 1')){$existing=$store->db->one('SELECT id,username,password,is_active,is_superuser FROM auth_user WHERE username=?',[$username]);if($existing&&$existing['is_active']&&Security::verifyPassword($password,$existing['password'])&&($existing['is_superuser']||$store->db->one("SELECT id FROM tenancy_tenantuser WHERE tenant_id=? AND user_id=? AND role='owner'",[$store->id(),$existing['id']])))return;throw new HttpError(409,'An administrator already exists. Enter the existing owner credentials to activate this migrated copy.');}
                        $salt=bin2hex(random_bytes(12));$encoded='pbkdf2_sha256$1000000$'.$salt.'$'.base64_encode(hash_pbkdf2('sha256',$password,$salt,1000000,32,true));
                        $user=$store->db->one('INSERT INTO auth_user(password,last_login,is_superuser,username,first_name,last_name,email,is_staff,is_active,date_joined) VALUES(?,NULL,FALSE,?,?,?,?,TRUE,TRUE,?) RETURNING id',[$encoded,$username,'','','',date('c')]);
                        $store->db->rows('INSERT INTO tenancy_tenantuser(role,created_at,tenant_id,user_id) VALUES(?,?,?,?)',['owner',date('c'),$store->id(),$user['id']]);
                    });$config['APP_URL']=$url;$config['complete']=true;unset($config['setup_token_hash']);self::save($config);$_SESSION=[];session_regenerate_id(true);redirect('/manage/login/');}
                    finally{flock($lock,LOCK_UN);fclose($lock);}
                }
            }
        }
        header('Content-Type: text/html; charset=utf-8');echo '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Set up Annam Foods</title><link rel="stylesheet" href="/assets/owner.css"><link rel="stylesheet" href="/assets/php.css"><main class="php-login"><h1>Set up Annam Foods</h1><p>Your database and images are stored on this hosting account. Create your admin login to open the store.</p>';
        if($error)echo '<p role="alert">'.e($error).'</p>';echo '<form method="post">'.csrf();foreach(['setup_code'=>'Private setup code','username'=>'Admin username','password'=>'Admin password','password_confirm'=>'Confirm password'] as $key=>$label)echo '<label class="o-field">'.e($label).'<input name="'.e($key).'" type="'.(str_starts_with($key,'password')?'password':'text').'" required autocomplete="'.(str_starts_with($key,'password')?'new-password':'off').'"></label>';echo '<button class="o-btn o-btn-primary">Finish setup</button></form></main></html>';
    }
}
