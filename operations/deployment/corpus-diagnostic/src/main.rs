#![allow(dead_code)]
mod types;

use serde_json::{Value, json};
use std::io::{Read, Write};

// Only these two value-less errors are referenced by the byte-identical types
// module. The production error enum is not needed for this pure classification.
pub enum Error { InvalidInput, InvalidBank }

const PUBLIC: &[u8] = include_bytes!("/nix/store/pdaay31fv76dxgmp1ar4xwhnbhb6fwyp-mrjam-reviewed-mrjam-qualified-artifacts-8bf05fb9065a-mateval/data/bank.json");
const MAXIMUM: u64 = 5 * 1024 * 1024;

fn classify(actual: Value) -> Result<Value, ()> {
    let expected: Value = serde_json::from_slice(PUBLIC).map_err(|_| ())?;
    let typed_expected: types::Bank = serde_json::from_value(expected.clone()).map_err(|_| ())?;
    typed_expected.validate().map_err(|_| ())?;
    let typed_actual: Result<types::Bank, _> = serde_json::from_value(actual.clone());
    let parsed = typed_actual.is_ok();
    let valid = typed_actual.as_ref().is_ok_and(|b| b.validate().is_ok());
    let typed = typed_actual.as_ref().ok().and_then(|b| serde_json::to_value(b).ok());
    let canonical_expected = serde_json::to_value(&typed_expected).map_err(|_| ())?;
    let questions = actual.get("questions").and_then(Value::as_array);
    let expected_questions = expected["questions"].as_array().ok_or(())?;
    let pairs = questions.filter(|q| q.len() == expected_questions.len());
    let all_questions = |fields: &[&str]| pairs.is_some_and(|qs| qs.iter().zip(expected_questions)
        .all(|(a, e)| fields.iter().all(|field| a.get(*field) == e.get(*field))));
    let all_productions = |field: &str| pairs.is_some_and(|qs| qs.iter().zip(expected_questions).all(|(a,e)| {
        match (a.get("productions").and_then(Value::as_array), e.get("productions").and_then(Value::as_array)) {
            (Some(ap),Some(ep)) if ap.len()==ep.len() => ap.iter().zip(ep).all(|(a,e)|a.get(field)==e.get(field)),
            _ => false,
        }
    }));
    let root_extra = actual.as_object().is_some_and(|m|m.keys().any(|k|!matches!(k.as_str(),"version"|"questions")));
    let question_extra = questions.is_some_and(|qs|qs.iter().any(|q|q.as_object().is_some_and(|m|
        m.keys().any(|k|!matches!(k.as_str(),"id"|"family"|"level"|"domain"|"statement"|"productions")))));
    let production_extra = questions.is_some_and(|qs|qs.iter().any(|q|q.get("productions").and_then(Value::as_array)
        .is_some_and(|ps|ps.iter().any(|p|p.as_object().is_some_and(|m|m.keys().any(|k|!matches!(k.as_str(),"id"|"content")))))));
    Ok(json!({"schema_version":1,"code":"MATHEVAL_TYPED_CORPUS_CLASSIFIED","checks":{
        "raw_json_equal":actual==expected,"typed_deserialization_accepted":parsed,"typed_validation_accepted":valid,
        "typed_json_equal":typed.as_ref()==Some(&canonical_expected),"version_equal":actual.get("version")==expected.get("version"),
        "question_count_equal":pairs.is_some(),"question_ids_and_order_equal":all_questions(&["id"]),
        "question_families_equal":all_questions(&["family"]),"question_levels_equal":all_questions(&["level"]),
        "question_domains_equal":all_questions(&["domain"]),"question_statements_equal":all_questions(&["statement"]),
        "production_ids_and_order_equal":all_productions("id"),"production_contents_equal":all_productions("content"),
        "extra_root_fields_present":root_extra,"extra_question_fields_present":question_extra,"extra_production_fields_present":production_extra
    },"corpus_values_exported":false,"codebook_read":false,"mutation_performed":false}))
}

fn main() {
    std::panic::set_hook(Box::new(|_| {}));
    let result = (|| {
        if std::env::args_os().len()!=1 {return Err(());}
        let mut bytes=Vec::new();
        std::io::stdin().lock().take(MAXIMUM+1).read_to_end(&mut bytes).map_err(|_|())?;
        if bytes.len() as u64>MAXIMUM {return Err(());}
        let value=serde_json::from_slice(&bytes).map_err(|_|())?;
        classify(value)
    })();
    let (value,status)=match result {Ok(v)=>(v,0),Err(())=>(json!({"schema_version":1,"code":"MATHEVAL_TYPED_CORPUS_REFUSED"}),1)};
    let mut output=std::io::stdout().lock();
    if serde_json::to_writer(&mut output,&value).is_err() || output.write_all(b"\n").is_err() {std::process::exit(1);}
    std::process::exit(status);
}
