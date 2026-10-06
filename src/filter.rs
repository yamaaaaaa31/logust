//! `filter=` of `logger.add()`: loguru's string and dict filters resolved in
//! Rust, plus the Python callable form.
//!
//! String and dict filters only look at the record's module `name` and level
//! number, so they are checked here without building the Python record dict
//! and without calling into Python.

use std::collections::HashMap;

use pyo3::exceptions::{PyTypeError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::{PyBool, PyDict, PyInt, PyString};

use crate::level::get_level_info;

/// A handler's `filter=`.
pub enum RecordFilter {
    /// A Python callable that receives the record dict (needs the GIL).
    Python(Py<PyAny>),
    /// A string or dict filter, checked in Rust.
    Native(NativeFilter),
}

impl RecordFilter {
    /// Parse `filter=` the way loguru does, raising `TypeError` / `ValueError`
    /// for invalid values. `None` and `""` mean no filter.
    pub fn from_py(obj: &Bound<'_, PyAny>) -> PyResult<Option<RecordFilter>> {
        if obj.is_none() {
            return Ok(None);
        }
        if obj.is_instance_of::<PyString>() || obj.is_instance_of::<PyDict>() {
            return Ok(NativeFilter::from_py(obj)?.map(RecordFilter::Native));
        }
        if obj.is_callable() {
            let builtin_filter = obj.py().import("builtins")?.getattr("filter")?;
            if obj.is(&builtin_filter) {
                return Err(PyValueError::new_err(
                    "The built-in 'filter()' function cannot be used as a 'filter' parameter, \
                     this is most likely a mistake (please double-check the arguments passed \
                     to 'logger.add()').",
                ));
            }
            return Ok(Some(RecordFilter::Python(obj.clone().unbind())));
        }
        Err(PyTypeError::new_err(format!(
            "Invalid filter, it should be a function, a string or a dict, not: '{}'",
            type_name(obj)
        )))
    }

    /// The Python callable, if this filter is one.
    #[inline]
    pub fn as_python(&self) -> Option<&Py<PyAny>> {
        match self {
            RecordFilter::Python(f) => Some(f),
            RecordFilter::Native(_) => None,
        }
    }

    /// The native filter, if this filter is one.
    #[inline]
    pub fn as_native(&self) -> Option<&NativeFilter> {
        match self {
            RecordFilter::Native(f) => Some(f),
            RecordFilter::Python(_) => None,
        }
    }
}

/// loguru's string (module) and dict (level per module) filters.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum NativeFilter {
    /// `filter="pkg"`: records from `pkg` and its submodules (`pkg.sub`), not `pkgx`.
    Module(String),
    /// `filter={"": "WARNING", "pkg": "DEBUG", "noisy": False}`.
    Levels(ModuleLevels),
}

impl NativeFilter {
    /// Parse a `str` or `dict` filter. `""` means no filter.
    pub fn from_py(obj: &Bound<'_, PyAny>) -> PyResult<Option<NativeFilter>> {
        if let Ok(s) = obj.cast::<PyString>() {
            let module = s.to_str()?;
            if module.is_empty() {
                return Ok(None);
            }
            return Ok(Some(NativeFilter::Module(module.to_owned())));
        }
        if let Ok(dict) = obj.cast::<PyDict>() {
            return Ok(Some(NativeFilter::Levels(ModuleLevels::from_py(dict)?)));
        }
        Err(PyTypeError::new_err(format!(
            "Invalid filter, it should be a string or a dict, not: '{}'",
            type_name(obj)
        )))
    }

    /// Whether a record from module `name` at severity `level_no` passes.
    #[inline]
    pub fn passes(&self, name: &str, level_no: u32) -> bool {
        match self {
            NativeFilter::Module(module) => module_matches(name, module),
            NativeFilter::Levels(levels) => levels.passes(name, level_no),
        }
    }
}

/// `name` is `module` or one of its submodules (`module.` prefix).
#[inline]
fn module_matches(name: &str, module: &str) -> bool {
    name.strip_prefix(module)
        .is_some_and(|rest| rest.is_empty() || rest.starts_with('.'))
}

/// Minimum level per module for a dict filter. `None` drops the module's records.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct ModuleLevels {
    levels: HashMap<String, Option<u32>>,
    /// loguru's `None` key: records without a module name (logust: an empty name).
    unnamed: Option<Option<u32>>,
}

impl ModuleLevels {
    fn from_py(dict: &Bound<'_, PyDict>) -> PyResult<ModuleLevels> {
        let mut out = ModuleLevels::default();
        for (key, value) in dict.iter() {
            let module: Option<String> = if key.is_none() {
                None
            } else if let Ok(s) = key.cast::<PyString>() {
                Some(s.to_str()?.to_owned())
            } else {
                return Err(PyTypeError::new_err(format!(
                    "The filter dict contains an invalid module, it should be a string \
                     (or None), not: '{}'",
                    type_name(&key)
                )));
            };
            let shown = module.as_deref().unwrap_or("None");
            let min = if let Ok(b) = value.cast::<PyBool>() {
                b.is_true().then_some(0)
            } else if let Ok(s) = value.cast::<PyString>() {
                let level_name = s.to_str()?;
                match get_level_info(level_name) {
                    Some(info) => Some(info.no),
                    None => {
                        return Err(PyValueError::new_err(format!(
                            "The filter dict contains a module '{shown}' associated to a level \
                             name which does not exist: '{level_name}'"
                        )));
                    }
                }
            } else if value.is_instance_of::<PyInt>() {
                // Out of i64 range: only the sign matters (huge means "nothing").
                let no: i64 =
                    value
                        .extract()
                        .unwrap_or(if value.lt(0)? { i64::MIN } else { i64::MAX });
                if no < 0 {
                    return Err(PyValueError::new_err(format!(
                        "The filter dict contains a module '{shown}' associated to an invalid \
                         level, it should be a positive integer, not: '{no}'"
                    )));
                }
                // Above every level: nothing from the module passes.
                Some(u32::try_from(no).unwrap_or(u32::MAX))
            } else {
                return Err(PyTypeError::new_err(format!(
                    "The filter dict contains a module '{shown}' associated to an invalid \
                     level, it should be an integer, a string or a boolean, not: '{}'",
                    type_name(&value)
                )));
            };
            match module {
                Some(m) => {
                    out.levels.insert(m, min);
                }
                None => out.unnamed = Some(min),
            }
        }
        Ok(out)
    }

    /// The closest parent module in the dict decides (`""` is the parent of
    /// all modules); a record with no matching key passes.
    pub fn passes(&self, name: &str, level_no: u32) -> bool {
        let check = |min: Option<u32>| min.is_some_and(|min| level_no >= min);
        if name.is_empty()
            && let Some(min) = self.unnamed
        {
            return check(min);
        }
        let mut name = name;
        loop {
            if let Some(&min) = self.levels.get(name) {
                return check(min);
            }
            if name.is_empty() {
                return true;
            }
            name = name.rfind('.').map_or("", |i| &name[..i]);
        }
    }
}

fn type_name(obj: &Bound<'_, PyAny>) -> String {
    obj.get_type()
        .name()
        .map_or_else(|_| "?".to_owned(), |n| n.to_string())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn levels(pairs: &[(&str, Option<u32>)]) -> ModuleLevels {
        ModuleLevels {
            levels: pairs.iter().map(|(k, v)| ((*k).to_owned(), *v)).collect(),
            unnamed: None,
        }
    }

    #[test]
    fn module_filter_matches_module_and_submodules_only() {
        let f = NativeFilter::Module("a.b".to_owned());
        assert!(f.passes("a.b", 0));
        assert!(f.passes("a.b.c", 0));
        assert!(!f.passes("a.bc", 0));
        assert!(!f.passes("a", 0));
        assert!(!f.passes("", 0));
        assert!(!f.passes("x.a.b", 0));
    }

    #[test]
    fn level_filter_uses_longest_prefix() {
        let l = levels(&[("", Some(30)), ("app", Some(10)), ("app.noisy", None)]);
        assert!(l.passes("app", 10));
        assert!(l.passes("app.core.db", 10));
        assert!(!l.passes("app.noisy", 50));
        assert!(!l.passes("app.noisy.sub", 50));
        assert!(l.passes("app.noisyx", 10));
        assert!(!l.passes("other", 20));
        assert!(l.passes("other", 30));
        assert!(!l.passes("", 20));
    }

    #[test]
    fn level_filter_without_match_passes() {
        let l = levels(&[("app", Some(40))]);
        assert!(l.passes("lib", 5));
        assert!(!l.passes("app.x", 30));
        assert!(ModuleLevels::default().passes("x", 0));
    }

    #[test]
    fn unnamed_key_applies_to_empty_names() {
        let mut l = levels(&[("", Some(10))]);
        l.unnamed = Some(None);
        assert!(!l.passes("", 50));
        assert!(l.passes("x", 10));
    }
}
