# Saved Garden progress

Anki Garden stores progress and settings in `anki-garden-data` inside Anki's
active data directory, alongside `addons21`. It uses Anki's configured location,
including a custom `-b` directory. All profiles in that directory share a garden;
separate Anki data directories remain independent.

After this version has started successfully, deleting and reinstalling the add-on
automatically resumes the last saved progress and settings. No export or restore
step is needed. The complete reward database is retained, including records that
prevent the same reviews or purchases from being rewarded twice.

The first startup copies older add-on-local progress and Anki-managed preferences
into a staged directory, verifies them, and publishes them together. Original
files are left untouched. Once the new store exists, it takes precedence over
any old installed copy. Migration/recovery snapshots stay with the durable data;
artwork caches can be recreated inside the add-on directory.

If Garden cannot read, preserve, or validate existing data, it stops instead of
starting an empty garden. Check the reported path, free disk space, and folder
permissions. Preserve damaged files and restore a known valid backup if needed.
Anki reviews remain available while Garden is stopped.

This protection does not recover data deleted before migration. It does not
survive loss of the computer or deletion of Anki's data directory, and it is not
an AnkiWeb/cloud backup. Keep ordinary computer backups. Older Garden versions
do not automatically read the new location; downgrades are not a recovery method.

Integrity checks detect corruption and inconsistent records. They do not prevent
deliberate editing of local files or add-on code. No account, server, signing key,
or encryption is required.
