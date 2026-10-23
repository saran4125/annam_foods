<?php
declare(strict_types=1);
namespace Annam;
final class ProviderError extends \RuntimeException {
    public function __construct(public readonly bool $uncertain=false) {parent::__construct('The provider could not confirm this request. Please retry the status check.');}
}
