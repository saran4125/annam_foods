<?php
declare(strict_types=1);
namespace Annam;

final class Database {
    private \PDO $connection;
    public function __construct(?\PDO $connection = null) {
        if ($connection) {
            $this->connection = $connection;
            $connection->setAttribute(\PDO::ATTR_DEFAULT_FETCH_MODE, \PDO::FETCH_ASSOC);
            $connection->setAttribute(\PDO::ATTR_ERRMODE, \PDO::ERRMODE_EXCEPTION);
            $connection->setAttribute(\PDO::ATTR_EMULATE_PREPARES, false);
            return;
        }
        $dsn = getenv('DATABASE_DSN') ?: '';
        if (!str_starts_with($dsn, 'pgsql:')) throw new \RuntimeException('Configure a PostgreSQL test database.');
        if (!str_contains($dsn, 'sslmode=')) $dsn .= ';sslmode=' . (getenv('DATABASE_SSLMODE') ?: 'require');
        $this->connection = new \PDO($dsn, getenv('DATABASE_USER') ?: '', getenv('DATABASE_PASSWORD') ?: '', [
            \PDO::ATTR_ERRMODE => \PDO::ERRMODE_EXCEPTION,
            \PDO::ATTR_EMULATE_PREPARES => false,
            \PDO::ATTR_DEFAULT_FETCH_MODE => \PDO::FETCH_ASSOC,
        ]);
    }
    public function rows(string $sql, array $params = []): array {
        $statement = $this->connection->prepare($sql);
        foreach ($params as $key => $value) {
            $type = is_bool($value) ? \PDO::PARAM_BOOL : (is_int($value) ? \PDO::PARAM_INT : ($value === null ? \PDO::PARAM_NULL : \PDO::PARAM_STR));
            $statement->bindValue(is_int($key) ? $key + 1 : $key, $value, $type);
        }
        $statement->execute();
        return $statement->columnCount() ? $statement->fetchAll() : [];
    }
    public function one(string $sql, array $params = []): ?array { return $this->rows($sql, $params)[0] ?? null; }
    public function transaction(callable $operation): mixed {
        $nested = $this->connection->inTransaction();
        $savepoint = 'annam_' . bin2hex(random_bytes(8));
        if ($nested) $this->connection->exec('SAVEPOINT ' . $savepoint);
        else $this->connection->beginTransaction();
        try {
            $result = $operation();
            if ($nested) $this->connection->exec('RELEASE SAVEPOINT ' . $savepoint);
            else $this->connection->commit();
            return $result;
        } catch (\Throwable $e) {
            if ($nested) { $this->connection->exec('ROLLBACK TO SAVEPOINT ' . $savepoint); $this->connection->exec('RELEASE SAVEPOINT ' . $savepoint); }
            else $this->connection->rollBack();
            throw $e;
        }
    }
}
