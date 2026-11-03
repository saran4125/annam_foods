<?php
declare(strict_types=1);
namespace Annam;

final class Database {
    private \PDO $connection;
    private bool $sqliteTransaction=false;
    public readonly string $driver;
    public readonly ?string $path;
    public function __construct(?\PDO $connection=null) {
        $path=null;
        if($connection)$this->connection=$connection;
        else{
            $dsn=getenv('DATABASE_DSN')?:'sqlite:storage/annam.sqlite';
            if(str_starts_with($dsn,'sqlite:')){
                $path=substr($dsn,7);if(!str_starts_with($path,'/'))$path=ANNAM_ROOT.'/'.$path;if(is_file($path))$path=realpath($path);
                if($path!==':memory:'&&(str_starts_with($path,ANNAM_ROOT.'/public/')||str_contains($path,'/public_html/')))throw new \RuntimeException('The database must be outside the public website.');
                if(!is_file($path))throw new \RuntimeException('The local database file is missing. Restore the bundled database or run the documented migration.');
                $this->connection=new \PDO('sqlite:'.$path);
            }elseif(str_starts_with($dsn,'pgsql:')){
                if(!str_contains($dsn,'sslmode='))$dsn.=';sslmode='.(getenv('DATABASE_SSLMODE')?:'require');
                if(getenv('APP_ENV')==='production'&&!preg_match('/(?:^|;)sslmode=(?:require|verify-ca|verify-full)(?:;|$)/',$dsn))throw new \RuntimeException('Production PostgreSQL connections require TLS.');
                $this->connection=new \PDO($dsn,getenv('DATABASE_USER')?:'',getenv('DATABASE_PASSWORD')?:'',[\PDO::ATTR_EMULATE_PREPARES=>false,\PDO::PGSQL_ATTR_DISABLE_PREPARES=>true]);
            }else throw new \RuntimeException('Choose the local SQLite file or the migration PostgreSQL connection.');
        }
        $this->connection->setAttribute(\PDO::ATTR_DEFAULT_FETCH_MODE,\PDO::FETCH_ASSOC);$this->connection->setAttribute(\PDO::ATTR_ERRMODE,\PDO::ERRMODE_EXCEPTION);$this->driver=$this->connection->getAttribute(\PDO::ATTR_DRIVER_NAME);$this->path=$path;
        if($this->isSqlite()){$this->connection->exec('PRAGMA foreign_keys=ON');$this->connection->exec('PRAGMA busy_timeout=15000');$this->connection->exec('PRAGMA journal_mode=WAL');$this->connection->exec('PRAGMA synchronous=FULL');SqliteDialect::register($this->connection);}
        else{$this->connection->exec("SET statement_timeout='30s'");$this->connection->exec("SET lock_timeout='5s'");}
    }
    public function isSqlite():bool{return $this->driver==='sqlite';}
    public function rows(string $sql,array $params=[]):array {
        if($this->isSqlite()){$params=SqliteDialect::parameters($sql,$params);$sql=SqliteDialect::sql($sql);}
        $statement=$this->connection->prepare($sql);
        foreach($params as $key=>$value){$type=is_bool($value)?\PDO::PARAM_BOOL:(is_int($value)?\PDO::PARAM_INT:($value===null?\PDO::PARAM_NULL:\PDO::PARAM_STR));$statement->bindValue(is_int($key)?$key+1:$key,$value,$type);}
        $statement->execute();$rows=$statement->columnCount()?$statement->fetchAll():[];return $this->isSqlite()?SqliteDialect::results($rows):$rows;
    }
    public function one(string $sql,array $params=[]):?array{return $this->rows($sql,$params)[0]??null;}
    public function schemaScript(string $sql):void{$this->connection->exec($sql);if(!$this->isSqlite())$this->connection->exec('SET search_path TO public');}
    public function transaction(callable $operation):mixed {
        $nested=$this->sqliteTransaction||$this->connection->inTransaction();$savepoint='annam_'.bin2hex(random_bytes(8));
        if($nested)$this->connection->exec('SAVEPOINT '.$savepoint);
        elseif($this->isSqlite()){$this->connection->exec('BEGIN IMMEDIATE');$this->sqliteTransaction=true;}
        else $this->connection->beginTransaction();
        try{$result=$operation();if($nested)$this->connection->exec('RELEASE SAVEPOINT '.$savepoint);elseif($this->isSqlite()){$this->connection->exec('COMMIT');$this->sqliteTransaction=false;}else $this->connection->commit();return $result;}
        catch(\Throwable $e){if($nested){$this->connection->exec('ROLLBACK TO SAVEPOINT '.$savepoint);$this->connection->exec('RELEASE SAVEPOINT '.$savepoint);}elseif($this->isSqlite()){$this->connection->exec('ROLLBACK');$this->sqliteTransaction=false;}else $this->connection->rollBack();throw $e;}
    }
    /** SQLite itself creates a consistent snapshot, including committed WAL data. */
    public function snapshot(string $destination):void {if(!$this->isSqlite()||file_exists($destination))throw new \RuntimeException('Choose a new SQLite snapshot destination.');$this->connection->exec('VACUUM INTO '.$this->connection->quote($destination));chmod($destination,0600);}
}
