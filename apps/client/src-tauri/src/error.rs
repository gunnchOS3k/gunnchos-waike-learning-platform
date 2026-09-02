//! Typed pack / storage errors surfaced to the UI without leaking secrets.

use serde::Serialize;
use thiserror::Error;

#[derive(Debug, Clone, Error, Serialize, PartialEq, Eq)]
#[serde(tag = "code", content = "detail")]
pub enum AppError {
    #[error("UNSIGNED_PACK")]
    UnsignedPack(String),
    #[error("MISSING_SIGNATURE")]
    MissingSignature(String),
    #[error("BAD_SIGNATURE")]
    BadSignature(String),
    #[error("TAMPERED_CONTENT")]
    TamperedContent(String),
    #[error("WRONG_ROLE")]
    WrongRole(String),
    #[error("INCOMPATIBLE_SCHEMA_MAJOR")]
    IncompatibleSchemaMajor(String),
    #[error("SCHEMA_DOWNGRADE")]
    SchemaDowngrade(String),
    #[error("UNKNOWN_MODULE")]
    UnknownModule(String),
    #[error("VERIFY_BEFORE_TRUST")]
    VerifyBeforeTrust(String),
    #[error("PLATFORM_TOO_OLD")]
    PlatformTooOld(String),
    #[error("INSTRUCTOR_MATERIAL_IN_LEARNER")]
    InstructorMaterialInLearner(String),
    #[error("PRIVATE_KEY_IN_LEARNER")]
    PrivateKeyInLearner(String),
    #[error("IO")]
    Io(String),
    #[error("DB")]
    Db(String),
    #[error("KEY")]
    Key(String),
    #[error("NOT_FOUND")]
    NotFound(String),
}

impl From<std::io::Error> for AppError {
    fn from(value: std::io::Error) -> Self {
        AppError::Io(value.to_string())
    }
}

impl From<rusqlite::Error> for AppError {
    fn from(value: rusqlite::Error) -> Self {
        AppError::Db(value.to_string())
    }
}

impl From<serde_json::Error> for AppError {
    fn from(value: serde_json::Error) -> Self {
        AppError::Io(value.to_string())
    }
}

impl From<zip::result::ZipError> for AppError {
    fn from(value: zip::result::ZipError) -> Self {
        AppError::Io(value.to_string())
    }
}

pub fn ui_code(err: &AppError) -> &'static str {
    match err {
        AppError::UnsignedPack(_) => "UNSIGNED_PACK",
        AppError::MissingSignature(_) => "MISSING_SIGNATURE",
        AppError::BadSignature(_) => "BAD_SIGNATURE",
        AppError::TamperedContent(_) => "TAMPERED_CONTENT",
        AppError::WrongRole(_) => "WRONG_ROLE",
        AppError::IncompatibleSchemaMajor(_) => "INCOMPATIBLE_SCHEMA_MAJOR",
        AppError::SchemaDowngrade(_) => "SCHEMA_DOWNGRADE",
        AppError::UnknownModule(_) => "UNKNOWN_MODULE",
        AppError::VerifyBeforeTrust(_) => "VERIFY_BEFORE_TRUST",
        AppError::PlatformTooOld(_) => "PLATFORM_TOO_OLD",
        AppError::InstructorMaterialInLearner(_) => "INSTRUCTOR_MATERIAL_IN_LEARNER",
        AppError::PrivateKeyInLearner(_) => "PRIVATE_KEY_IN_LEARNER",
        AppError::Io(_) => "IO",
        AppError::Db(_) => "DB",
        AppError::Key(_) => "KEY",
        AppError::NotFound(_) => "NOT_FOUND",
    }
}
