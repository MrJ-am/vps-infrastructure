//! Bounded local reads. Public assets are checked then retained in memory.
use rustix::fs::{Mode, OFlags, StatVfsMountFlags, fgetxattr, fstatvfs, open, openat};
use sha2::{Digest, Sha256};
use std::{
    fs::File,
    io::Read,
    os::unix::fs::MetadataExt,
    path::{Component, Path},
};

pub fn read_regular(path: &Path, maximum: usize, private: bool) -> Result<Vec<u8>, &'static str> {
    if !path.is_absolute()
        || path
            .components()
            .any(|part| matches!(part, Component::ParentDir | Component::CurDir))
    {
        return Err("INVALID_FILE_REFERENCE");
    }
    // Walk from a stable directory descriptor. No pathname parent can be
    // replaced with a symlink between checking and opening the final file.
    let components: Vec<_> = path
        .components()
        .filter_map(|part| {
            if let Component::Normal(name) = part {
                Some(name)
            } else {
                None
            }
        })
        .collect();
    let (name, parents) = components.split_last().ok_or("INVALID_FILE_REFERENCE")?;
    let mut directory = open(
        "/",
        OFlags::RDONLY | OFlags::DIRECTORY | OFlags::NOFOLLOW | OFlags::CLOEXEC,
        Mode::empty(),
    )
    .map_err(|_| "FILE_REFERENCE_UNAVAILABLE")?;
    for parent in parents {
        directory = openat(
            &directory,
            Path::new(parent),
            OFlags::RDONLY | OFlags::DIRECTORY | OFlags::NOFOLLOW | OFlags::CLOEXEC,
            Mode::empty(),
        )
        .map_err(|_| "FILE_REFERENCE_UNAVAILABLE")?;
    }
    let descriptor = openat(
        &directory,
        Path::new(name),
        OFlags::RDONLY | OFlags::NONBLOCK | OFlags::NOFOLLOW | OFlags::CLOEXEC,
        Mode::empty(),
    )
    .map_err(|_| "FILE_REFERENCE_UNAVAILABLE")?;
    let mut file = File::from(descriptor);
    let directory = File::from(directory);
    let metadata = file.metadata().map_err(|_| "FILE_REFERENCE_UNAVAILABLE")?;
    if !metadata.is_file()
        || metadata.len() > maximum as u64
        || (private
            && metadata.mode() & 0o077 != 0
            && !systemd_credential_acl(&file, &directory, &metadata))
    {
        return Err("FILE_REFERENCE_REFUSED");
    }
    let mut bytes = Vec::new();
    (&mut file)
        .take(maximum as u64 + 1)
        .read_to_end(&mut bytes)
        .map_err(|_| "FILE_REFERENCE_UNAVAILABLE")?;
    if bytes.len() > maximum || bytes.len() as u64 != metadata.len() {
        return Err("FILE_REFERENCE_REFUSED");
    }
    Ok(bytes)
}

fn exact_acl(bytes: &[u8], uid: u32, permissions: u16) -> bool {
    if bytes.len() != 44 || bytes[..4] != 2u32.to_le_bytes() {
        return false;
    }
    let expected = [
        (1, permissions, u32::MAX),
        (2, permissions, uid),
        (4, 0, u32::MAX),
        (16, permissions, u32::MAX),
        (32, 0, u32::MAX),
    ];
    bytes[4..].as_chunks::<8>().0.iter().zip(expected).all(
        |(entry, (tag, permission, identity))| {
            u16::from_le_bytes([entry[0], entry[1]]) == tag
                && u16::from_le_bytes([entry[2], entry[3]]) == permission
                && u32::from_le_bytes([entry[4], entry[5], entry[6], entry[7]]) == identity
        },
    )
}

fn descriptor_acl(file: &File, uid: u32, permissions: u16) -> bool {
    let mut bytes = [0u8; 128];
    match fgetxattr(file, "system.posix_acl_access", &mut bytes[..]) {
        Ok(size) => exact_acl(&bytes[..size], uid, permissions),
        Err(_) => false,
    }
}

fn systemd_credential_acl(file: &File, directory: &File, metadata: &std::fs::Metadata) -> bool {
    // systemd 260.5 LoadCredential uses root-owned ACLs: mode 0440 reflects
    // the named-user ACL mask, not a grant to the owning group. Accept only
    // that exact measured shape, current EUID, stable parent and read-only mount.
    let uid = rustix::process::geteuid().as_raw();
    let Ok(parent) = directory.metadata() else {
        return false;
    };
    uid != 0
        && metadata.uid() == 0
        && metadata.gid() == 0
        && metadata.mode() & 0o7777 == 0o440
        && metadata.nlink() == 1
        && parent.uid() == 0
        && parent.gid() == 0
        && parent.mode() & 0o7777 == 0o550
        && fstatvfs(file).is_ok_and(|value| value.f_flag.contains(StatVfsMountFlags::RDONLY))
        && fstatvfs(directory).is_ok_and(|value| value.f_flag.contains(StatVfsMountFlags::RDONLY))
        && descriptor_acl(file, uid, 4)
        && descriptor_acl(directory, uid, 5)
}

pub fn credential(path: &Path) -> Result<String, &'static str> {
    let bytes = read_regular(path, 4096, true)?;
    let text = String::from_utf8(bytes).map_err(|_| "INVALID_CREDENTIAL_FILE")?;
    let value = text.strip_suffix('\n').unwrap_or(&text);
    if value.is_empty() || value.chars().any(char::is_control) {
        return Err("INVALID_CREDENTIAL_FILE");
    }
    Ok(value.to_owned())
}

pub fn digest(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

#[cfg(test)]
mod tests {
    use super::exact_acl;
    #[test]
    fn systemd_acl_shape_accepts_only_the_named_user_and_no_group_rights() {
        let uid = 64551;
        let mut value = 2u32.to_le_bytes().to_vec();
        for (tag, permission, identity) in [
            (1u16, 4u16, u32::MAX),
            (2, 4, uid),
            (4, 0, u32::MAX),
            (16, 4, u32::MAX),
            (32, 0, u32::MAX),
        ] {
            value.extend_from_slice(&tag.to_le_bytes());
            value.extend_from_slice(&permission.to_le_bytes());
            value.extend_from_slice(&identity.to_le_bytes());
        }
        assert!(exact_acl(&value, uid, 4));
        assert!(!exact_acl(&value, uid + 1, 4));
        assert!(!exact_acl(&value, uid, 5));
        let mut group = value.clone();
        group[22] = 4;
        assert!(!exact_acl(&group, uid, 4));
        let mut other = value.clone();
        other[38] = 4;
        assert!(!exact_acl(&other, uid, 4));
        value.extend_from_slice(&[0; 8]);
        assert!(!exact_acl(&value, uid, 4));
    }
}
