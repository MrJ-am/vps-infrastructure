-- Ne s'exécute pas dans une transaction ; échoue si la base existe déjà.
CREATE DATABASE vision_journal OWNER vision_journal_owner TEMPLATE template0
 ENCODING 'UTF8' LOCALE_PROVIDER libc LC_COLLATE 'C' LC_CTYPE 'C';
REVOKE ALL ON DATABASE vision_journal FROM PUBLIC;
GRANT CONNECT ON DATABASE vision_journal TO vision_journal_writer,
 vision_journal_archiviste,vision_journal_rejeu,vision_journal_fermeture,
 vision_journal_import;
