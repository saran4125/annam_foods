FROM wordpress:7.1.2-php8.3-fpm
RUN docker-php-ext-install bcmath
RUN curl -fsSL --max-time 90 --retry 2 https://github.com/wp-cli/wp-cli/releases/download/v2.12.0/wp-cli-2.12.0.phar -o /usr/local/bin/wp \
    && php /usr/local/bin/wp --info --allow-root
WORKDIR /var/www/html
