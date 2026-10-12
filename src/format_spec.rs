//! Python's format-spec mini-language for format template fields.
//!
//! `{line:05d}`, `{level: <8}`, `{message:>20.10}` and so on render as
//! `format(value, spec)` does in Python:
//! `[[fill]align][sign][z][#][0][width][grouping][.precision[grouping]][type]`.
//!
//! A spec is parsed once, when the template is compiled, for the kind of value
//! the field holds (`str` or `int`); errors carry Python's `ValueError` message.
//! Rendering then only lays out the value. Widths count characters (Unicode
//! code points), as in Python.
//!
//! Integer fields also accept the float presentation types (`e`, `f`, `g`, `%`
//! ...): Python converts the int to a float first, and so does this module. An
//! int converted to a float is an integral value, so the digits are produced
//! exactly with integer arithmetic (correctly rounded, ties to even, as Python's
//! `dtoa` does).
//!
//! Parsing follows CPython 3.14 (`Python/formatter_unicode.c`), including the
//! fractional-part grouping of 3.14 (`{line:.6_f}`).

/// Kind of value a field formats as
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ValueKind {
    /// Text (`str` in Python)
    Str,
    /// Integer (`int` in Python)
    Int,
}

impl ValueKind {
    fn type_name(self) -> &'static str {
        match self {
            ValueKind::Str => "str",
            ValueKind::Int => "int",
        }
    }
}

/// Where padding goes
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Align {
    /// `<`
    Left,
    /// `>`
    Right,
    /// `^` (extra padding on the right)
    Center,
    /// `=`: between the sign/prefix and the digits
    AfterSign,
}

impl Align {
    fn from_char(c: char) -> Option<Align> {
        match c {
            '<' => Some(Align::Left),
            '>' => Some(Align::Right),
            '^' => Some(Align::Center),
            '=' => Some(Align::AfterSign),
            _ => None,
        }
    }
}

/// A parsed format spec, resolved for one [`ValueKind`]
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct FormatSpec {
    fill: char,
    align: Align,
    /// `'+'`, `' '`, or `None` for the default (`'-'`: only negative numbers get a sign)
    sign: Option<char>,
    alternate: bool,
    width: usize,
    /// Thousands separator of the integer part and its group size
    grouping: Option<(char, usize)>,
    precision: Option<usize>,
    /// Separator of the fractional part (groups of 3, float types only)
    frac_grouping: Option<char>,
    /// Presentation type (`'s'` for strings, `'d'` by default for ints)
    ty: char,
}

/// Spec fields as written, before resolving them for a value kind
struct RawSpec {
    fill: Option<char>,
    align: Option<Align>,
    sign: Option<char>,
    no_neg_zero: bool,
    alternate: bool,
    zero: bool,
    width: usize,
    thousands: Option<char>,
    precision: Option<usize>,
    frac_thousands: Option<char>,
    ty: Option<char>,
}

fn too_many_digits() -> String {
    "Too many decimal digits in format string".to_string()
}

fn invalid_comma_and_underscore() -> String {
    "Cannot specify both ',' and '_'.".to_string()
}

/// `c` as CPython quotes a presentation type in error messages
fn quote_type(c: char) -> String {
    if c > ' ' && c < '\u{7f}' {
        format!("'{c}'")
    } else {
        format!("'\\x{:x}'", c as u32)
    }
}

fn unknown_presentation_type(ty: char, kind: ValueKind) -> String {
    format!(
        "Unknown format code {} for object of type '{}'",
        quote_type(ty),
        kind.type_name()
    )
}

/// Read a run of ASCII digits starting at `*pos`: `Ok(None)` if there is none
fn get_integer(chars: &[char], pos: &mut usize) -> Result<Option<usize>, String> {
    let mut value: usize = 0;
    let mut consumed = false;
    while let Some(digit) = chars.get(*pos).and_then(|c| c.to_digit(10)) {
        value = value
            .checked_mul(10)
            .and_then(|v| v.checked_add(digit as usize))
            .filter(|&v| v <= isize::MAX as usize)
            .ok_or_else(too_many_digits)?;
        consumed = true;
        *pos += 1;
    }
    Ok(consumed.then_some(value))
}

/// Parse `spec` like CPython's `parse_internal_render_format_spec`
fn parse_raw(spec: &str, kind: ValueKind) -> Result<RawSpec, String> {
    let chars: Vec<char> = spec.chars().collect();
    let end = chars.len();
    let mut pos = 0;
    let mut raw = RawSpec {
        fill: None,
        align: None,
        sign: None,
        no_neg_zero: false,
        alternate: false,
        zero: false,
        width: 0,
        thousands: None,
        precision: None,
        frac_thousands: None,
        ty: None,
    };

    // [[fill]align]
    if end >= 2
        && let Some(align) = Align::from_char(chars[1])
    {
        raw.fill = Some(chars[0]);
        raw.align = Some(align);
        pos = 2;
    } else if let Some(align) = chars.first().copied().and_then(Align::from_char) {
        raw.align = Some(align);
        pos = 1;
    }

    // [sign]
    if let Some(&c @ ('+' | '-' | ' ')) = chars.get(pos) {
        raw.sign = Some(c);
        pos += 1;
    }
    // [z]
    if chars.get(pos) == Some(&'z') {
        raw.no_neg_zero = true;
        pos += 1;
    }
    // [#]
    if chars.get(pos) == Some(&'#') {
        raw.alternate = true;
        pos += 1;
    }
    // [0]: zero padding, unless a fill character was given
    if raw.fill.is_none() && chars.get(pos) == Some(&'0') {
        raw.zero = true;
        pos += 1;
    }
    // [width]
    raw.width = get_integer(&chars, &mut pos)?.unwrap_or(0);

    // [grouping]
    if chars.get(pos) == Some(&',') {
        raw.thousands = Some(',');
        pos += 1;
    }
    if chars.get(pos) == Some(&'_') {
        if raw.thousands.is_some() {
            return Err(invalid_comma_and_underscore());
        }
        raw.thousands = Some('_');
        pos += 1;
    }
    if chars.get(pos) == Some(&',') && raw.thousands == Some('_') {
        return Err(invalid_comma_and_underscore());
    }

    // [.precision[grouping]]
    if chars.get(pos) == Some(&'.') {
        pos += 1;
        raw.precision = get_integer(&chars, &mut pos)?;
        if chars.get(pos) == Some(&',') {
            raw.frac_thousands = Some(',');
            pos += 1;
        }
        if chars.get(pos) == Some(&'_') {
            if raw.frac_thousands.is_some() {
                return Err(invalid_comma_and_underscore());
            }
            raw.frac_thousands = Some('_');
            pos += 1;
        }
        if chars.get(pos) == Some(&',') && raw.frac_thousands == Some('_') {
            return Err(invalid_comma_and_underscore());
        }
        if raw.precision.is_none() && raw.frac_thousands.is_none() {
            return Err("Format specifier missing precision".to_string());
        }
    }

    // [type]
    if end - pos > 1 {
        return Err(format!(
            "Invalid format specifier '{spec}' for object of type '{}'",
            kind.type_name()
        ));
    }
    raw.ty = chars.get(pos).copied();

    if let Some(sep) = raw.thousands {
        let ty = raw.ty.unwrap_or(match kind {
            ValueKind::Str => 's',
            ValueKind::Int => 'd',
        });
        let allowed = match ty {
            'd' | 'e' | 'f' | 'g' | 'E' | 'G' | '%' | 'F' => true,
            'b' | 'o' | 'x' | 'X' => sep == '_',
            _ => false,
        };
        if !allowed {
            return Err(format!("Cannot specify '{sep}' with {}.", quote_type(ty)));
        }
    }
    Ok(raw)
}

impl FormatSpec {
    /// Parse `spec` for a value of `kind`, with Python's error message if
    /// `format(value, spec)` would raise for any value of that kind.
    pub fn parse(spec: &str, kind: ValueKind) -> Result<FormatSpec, String> {
        let raw = parse_raw(spec, kind)?;
        match kind {
            ValueKind::Str => Self::resolve_str(raw),
            ValueKind::Int => Self::resolve_int(raw),
        }
    }

    fn resolve_str(raw: RawSpec) -> Result<FormatSpec, String> {
        let ty = raw.ty.unwrap_or('s');
        if ty != 's' {
            return Err(unknown_presentation_type(ty, ValueKind::Str));
        }
        match raw.sign {
            Some(' ') => return Err("Space not allowed in string format specifier".to_string()),
            Some(_) => return Err("Sign not allowed in string format specifier".to_string()),
            None => {}
        }
        if raw.no_neg_zero {
            return Err(
                "Negative zero coercion (z) not allowed in string format specifier".to_string(),
            );
        }
        if raw.alternate {
            return Err("Alternate form (#) not allowed in string format specifier".to_string());
        }
        if raw.align == Some(Align::AfterSign) {
            return Err("'=' alignment not allowed in string format specifier".to_string());
        }
        Ok(FormatSpec {
            fill: raw.fill.unwrap_or(if raw.zero { '0' } else { ' ' }),
            align: raw.align.unwrap_or(Align::Left),
            sign: None,
            alternate: false,
            width: raw.width,
            grouping: None,
            precision: raw.precision,
            frac_grouping: None,
            ty,
        })
    }

    fn resolve_int(raw: RawSpec) -> Result<FormatSpec, String> {
        let ty = raw.ty.unwrap_or('d');
        match ty {
            'b' | 'c' | 'd' | 'o' | 'x' | 'X' | 'n' => {
                if raw.precision.is_some() {
                    return Err("Precision not allowed in integer format specifier".to_string());
                }
                if raw.no_neg_zero {
                    return Err(
                        "Negative zero coercion (z) not allowed in integer format specifier"
                            .to_string(),
                    );
                }
                if ty == 'c' {
                    if raw.sign.is_some() {
                        return Err("Sign not allowed with integer format specifier 'c'".into());
                    }
                    if raw.alternate {
                        return Err(
                            "Alternate form (#) not allowed with integer format specifier 'c'"
                                .into(),
                        );
                    }
                }
            }
            'e' | 'E' | 'f' | 'F' | 'g' | 'G' | '%' => {}
            _ => return Err(unknown_presentation_type(ty, ValueKind::Int)),
        }
        let group_size = if matches!(ty, 'b' | 'o' | 'x' | 'X') {
            4
        } else {
            3
        };
        let align = match raw.align {
            Some(align) => align,
            None if raw.zero => Align::AfterSign,
            None => Align::Right,
        };
        Ok(FormatSpec {
            fill: raw.fill.unwrap_or(if raw.zero { '0' } else { ' ' }),
            align,
            sign: raw.sign.filter(|&c| c != '-'),
            alternate: raw.alternate,
            width: raw.width,
            grouping: raw.thousands.map(|sep| (sep, group_size)),
            precision: raw.precision,
            frac_grouping: raw.frac_thousands,
            ty,
        })
    }

    /// The spec is exactly `<N` / ` <N`: left-align in N columns with spaces
    pub fn left_pad_width(&self) -> Option<usize> {
        (self.fill == ' '
            && self.align == Align::Left
            && self.precision.is_none()
            && self.grouping.is_none()
            && self.ty == 's')
            .then_some(self.width)
    }

    /// Whether rendering `text` cuts it (a precision shorter than the text)
    pub fn truncates(&self, text: &str) -> bool {
        self.precision
            .is_some_and(|precision| text.chars().nth(precision).is_some())
    }

    /// Padding (left, right) around a value `len` characters wide
    fn padding(&self, len: usize) -> (usize, usize) {
        let pad = self.width.saturating_sub(len);
        match self.align {
            Align::Left => (0, pad),
            Align::Right | Align::AfterSign => (pad, 0),
            Align::Center => (pad / 2, pad - pad / 2),
        }
    }

    fn push_fill(&self, out: &mut String, count: usize) {
        for _ in 0..count {
            out.push(self.fill);
        }
    }

    /// Append `text` formatted like `format(text, spec)` (spec parsed for `str`)
    pub fn write_str(&self, out: &mut String, text: &str) {
        let text = match self.precision {
            Some(precision) => match text.char_indices().nth(precision) {
                Some((cut, _)) => &text[..cut],
                None => text,
            },
            None => text,
        };
        if self.width == 0 {
            out.push_str(text);
            return;
        }
        let (left, right) = self.padding(text.chars().count());
        self.push_fill(out, left);
        out.push_str(text);
        self.push_fill(out, right);
    }

    /// Append `styled`, the styled rendering of `plain`, padded as
    /// `format(plain, spec)` pads `plain` (escape codes take no width).
    ///
    /// Only valid when the spec doesn't cut `plain` (see [`FormatSpec::truncates`]).
    pub fn write_str_around(&self, out: &mut String, plain: &str, styled: &str) {
        let (left, right) = self.padding(plain.chars().count());
        self.push_fill(out, left);
        out.push_str(styled);
        self.push_fill(out, right);
    }

    /// Append the unsigned integer `value` formatted like `format(value, spec)`
    /// (spec parsed for `int`). Returns false (writing nothing) if Python would
    /// raise for this value (`c` out of the Unicode range).
    pub fn write_uint(&self, out: &mut String, value: u64) -> bool {
        self.write_int(out, false, u128::from(value))
    }

    /// Append the integer `-magnitude` / `magnitude` like `format(value, spec)`
    fn write_int(&self, out: &mut String, negative: bool, magnitude: u128) -> bool {
        let mut digits = String::new();
        let prefix = match self.ty {
            'd' | 'n' => {
                push_radix(&mut digits, magnitude, 10, false);
                ""
            }
            'b' => {
                push_radix(&mut digits, magnitude, 2, false);
                "0b"
            }
            'o' => {
                push_radix(&mut digits, magnitude, 8, false);
                "0o"
            }
            'x' => {
                push_radix(&mut digits, magnitude, 16, false);
                "0x"
            }
            'X' => {
                push_radix(&mut digits, magnitude, 16, true);
                "0X"
            }
            'c' => {
                let ch = u32::try_from(magnitude)
                    .ok()
                    .filter(|_| !negative)
                    .and_then(char::from_u32);
                let Some(ch) = ch else {
                    return false;
                };
                let mut remainder = [0u8; 4];
                let remainder = ch.encode_utf8(&mut remainder);
                self.write_number(out, false, "", "", None, remainder);
                return true;
            }
            _ => {
                self.write_float(out, negative, magnitude);
                return true;
            }
        };
        let prefix = if self.alternate { prefix } else { "" };
        self.write_number(out, negative, prefix, &digits, None, "");
        true
    }

    /// An int in a float presentation: Python formats `float(value)`
    fn write_float(&self, out: &mut String, negative: bool, magnitude: u128) {
        // Python's int -> float conversion rounds to nearest, ties to even, as `as` does
        let mut value = magnitude as f64;
        if self.ty == '%' {
            // Same double multiplication as CPython
            value *= 100.0;
        }
        // Integral (an int's float stays integral, and so does * 100), and
        // below 2^128 for any u64 * 100
        let n = value as u128;
        let upper = self.ty.is_ascii_uppercase();
        let precision = self.precision.unwrap_or(6);
        let mut int_part = String::new();
        let mut frac = String::new();
        let decimal;
        let mut remainder = String::new();
        match self.ty {
            'f' | 'F' | '%' => {
                push_radix(&mut int_part, n, 10, false);
                decimal = precision > 0 || self.alternate;
                frac.extend(std::iter::repeat_n('0', precision));
                if self.ty == '%' {
                    remainder.push('%');
                }
            }
            'e' | 'E' => {
                let (mantissa, exp) = round_significant(n, precision + 1);
                int_part.push(char::from(mantissa[0]));
                frac.extend(mantissa[1..].iter().map(|&d| char::from(d)));
                decimal = precision > 0 || self.alternate;
                push_exponent(&mut remainder, exp, upper);
            }
            _ => {
                // 'g' / 'G'
                let precision = precision.max(1);
                let (mut sig, exp) = round_significant(n, precision);
                if !self.alternate {
                    while sig.len() > 1 && sig.last() == Some(&b'0') {
                        sig.pop();
                    }
                }
                if exp >= precision {
                    int_part.push(char::from(sig[0]));
                    frac.extend(sig[1..].iter().map(|&d| char::from(d)));
                    push_exponent(&mut remainder, exp, upper);
                } else {
                    // `exp + 1` integer digits; `n` has at most `precision` digits here
                    push_radix(&mut int_part, n, 10, false);
                    let frac_digits = if self.alternate {
                        precision - (exp + 1)
                    } else {
                        sig.len().saturating_sub(exp + 1)
                    };
                    frac.extend(std::iter::repeat_n('0', frac_digits));
                }
                decimal = !frac.is_empty() || self.alternate;
            }
        }
        if let Some(sep) = self.frac_grouping {
            frac = group_left(&frac, sep);
        }
        let frac = decimal.then_some(frac.as_str());
        self.write_number(out, negative, "", &int_part, frac, &remainder);
    }

    /// Lay out a number like CPython's `calc_number_widths` + `fill_number`:
    /// `<lpad><sign><prefix><spad><grouped digits>[.<frac>]<remainder><rpad>`
    fn write_number(
        &self,
        out: &mut String,
        negative: bool,
        prefix: &str,
        digits: &str,
        frac: Option<&str>,
        remainder: &str,
    ) {
        let sign = if negative { Some('-') } else { self.sign };
        let n_frac = frac.map_or(0, |f| 1 + f.len());
        let non_digit =
            usize::from(sign.is_some()) + prefix.len() + n_frac + remainder.chars().count();
        let min_width = if self.fill == '0' && self.align == Align::AfterSign {
            self.width as isize - non_digit as isize
        } else {
            0
        };
        let grouped = if digits.is_empty() {
            String::new()
        } else {
            insert_grouping(digits, min_width, self.grouping)
        };
        let (left, right) = self.padding(non_digit + grouped.len());
        let (left, middle) = if self.align == Align::AfterSign {
            (0, left)
        } else {
            (left, 0)
        };
        self.push_fill(out, left);
        if let Some(sign) = sign {
            out.push(sign);
        }
        out.push_str(prefix);
        self.push_fill(out, middle);
        out.push_str(&grouped);
        if let Some(frac) = frac {
            out.push('.');
            out.push_str(frac);
        }
        out.push_str(remainder);
        self.push_fill(out, right);
    }
}

/// Append `value` in `radix` (2, 8, 10 or 16)
fn push_radix(out: &mut String, mut value: u128, radix: u128, upper: bool) {
    let table: &[u8; 16] = if upper {
        b"0123456789ABCDEF"
    } else {
        b"0123456789abcdef"
    };
    let mut buf = [0u8; 128];
    let mut start = buf.len();
    loop {
        start -= 1;
        buf[start] = table[(value % radix) as usize];
        value /= radix;
        if value == 0 {
            break;
        }
    }
    out.extend(buf[start..].iter().map(|&b| char::from(b)));
}

/// `n` rounded to `count` significant decimal digits (ties to even), as
/// (digits, exponent of the first digit)
fn round_significant(n: u128, count: usize) -> (Vec<u8>, usize) {
    let mut decimal = String::new();
    push_radix(&mut decimal, n, 10, false);
    let digits = decimal.as_bytes();
    let mut exp = digits.len() - 1;
    if digits.len() <= count {
        let mut sig = digits.to_vec();
        sig.resize(count, b'0');
        return (sig, exp);
    }
    let mut sig = digits[..count].to_vec();
    let rest = &digits[count..];
    let round_up = match rest[0] {
        b'6'..=b'9' => true,
        b'5' => {
            rest[1..].iter().any(|&d| d != b'0') || sig.last().is_some_and(|&d| (d - b'0') % 2 == 1)
        }
        _ => false,
    };
    if round_up {
        let mut i = sig.len();
        loop {
            if i == 0 {
                // All nines: 99.9 -> 100
                sig.insert(0, b'1');
                sig.pop();
                exp += 1;
                break;
            }
            i -= 1;
            if sig[i] == b'9' {
                sig[i] = b'0';
            } else {
                sig[i] += 1;
                break;
            }
        }
    }
    (sig, exp)
}

/// Append Python's exponent suffix: `e+05`, `E+21`
fn push_exponent(out: &mut String, exp: usize, upper: bool) {
    out.push(if upper { 'E' } else { 'e' });
    out.push('+');
    if exp < 10 {
        out.push('0');
    }
    push_radix(out, exp as u128, 10, false);
}

/// Fractional digits with `sep` after every 3 digits from the left
fn group_left(frac: &str, sep: char) -> String {
    let mut out = String::with_capacity(frac.len() + frac.len() / 3);
    for (i, c) in frac.chars().enumerate() {
        if i > 0 && i % 3 == 0 {
            out.push(sep);
        }
        out.push(c);
    }
    out
}

/// Insert thousands separators into `digits`, zero-padding the digits to
/// `min_width` characters (separators included), like CPython's
/// `_PyUnicode_InsertThousandsGrouping`. `grouping` is (separator, group size);
/// None groups nothing (and only pads).
fn insert_grouping(digits: &str, min_width: isize, grouping: Option<(char, usize)>) -> String {
    let (sep, group) = match grouping {
        Some((sep, size)) => (Some(sep), size as isize),
        None => (None, isize::MAX),
    };
    let sep_len = isize::from(sep.is_some());
    let bytes = digits.as_bytes();
    let mut remaining = bytes.len() as isize;
    let mut min_width = min_width;
    // Groups from the right
    let mut groups: Vec<(usize, &[u8])> = Vec::new();
    loop {
        let l = group.min(remaining.max(min_width).max(1));
        let n_zeros = (l - remaining).max(0) as usize;
        let n_chars = remaining.min(l).max(0) as usize;
        let start = remaining.max(0) as usize - n_chars;
        groups.push((n_zeros, &bytes[start..start + n_chars]));
        remaining -= n_chars as isize;
        min_width -= l;
        if remaining <= 0 && min_width <= 0 {
            break;
        }
        min_width -= sep_len;
    }
    let mut out = String::with_capacity(bytes.len() + groups.len() * 2);
    for (i, (zeros, chars)) in groups.iter().rev().enumerate() {
        if i > 0
            && let Some(sep) = sep
        {
            out.push(sep);
        }
        out.extend(std::iter::repeat_n('0', *zeros));
        out.extend(chars.iter().map(|&b| char::from(b)));
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    fn fmt_str(text: &str, spec: &str) -> Result<String, String> {
        let spec = FormatSpec::parse(spec, ValueKind::Str)?;
        let mut out = String::new();
        spec.write_str(&mut out, text);
        Ok(out)
    }

    fn fmt_int(value: u64, spec: &str) -> Result<String, String> {
        let spec = FormatSpec::parse(spec, ValueKind::Int)?;
        let mut out = String::new();
        assert!(spec.write_uint(&mut out, value));
        Ok(out)
    }

    #[test]
    fn parse_fill_align_width() {
        let spec = FormatSpec::parse("*^9", ValueKind::Str).unwrap();
        assert_eq!(spec.fill, '*');
        assert_eq!(spec.align, Align::Center);
        assert_eq!(spec.width, 9);
        let spec = FormatSpec::parse(" <8", ValueKind::Str).unwrap();
        assert_eq!(spec.left_pad_width(), Some(8));
        let spec = FormatSpec::parse("<8", ValueKind::Str).unwrap();
        assert_eq!(spec.left_pad_width(), Some(8));
        let spec = FormatSpec::parse(">8", ValueKind::Str).unwrap();
        assert_eq!(spec.left_pad_width(), None);
        // An align character alone is the align, not a fill
        let spec = FormatSpec::parse("<", ValueKind::Str).unwrap();
        assert_eq!((spec.fill, spec.align, spec.width), (' ', Align::Left, 0));
        // A fill that is itself an align character
        let spec = FormatSpec::parse("<<5", ValueKind::Str).unwrap();
        assert_eq!((spec.fill, spec.align), ('<', Align::Left));
    }

    #[test]
    fn parse_zero_flag() {
        let spec = FormatSpec::parse("05", ValueKind::Int).unwrap();
        assert_eq!(
            (spec.fill, spec.align, spec.width),
            ('0', Align::AfterSign, 5)
        );
        let spec = FormatSpec::parse("05", ValueKind::Str).unwrap();
        assert_eq!((spec.fill, spec.align, spec.width), ('0', Align::Left, 5));
        // With an explicit fill the 0 is part of the width
        let spec = FormatSpec::parse("x<05", ValueKind::Int).unwrap();
        assert_eq!((spec.fill, spec.width), ('x', 5));
        // An explicit align keeps the zero fill but not the '=' align
        let spec = FormatSpec::parse("<05", ValueKind::Int).unwrap();
        assert_eq!((spec.fill, spec.align), ('0', Align::Left));
    }

    #[test]
    fn parse_grouping_precision_type() {
        let spec = FormatSpec::parse("+#,.3e", ValueKind::Int).unwrap();
        assert_eq!(spec.sign, Some('+'));
        assert!(spec.alternate);
        assert_eq!(spec.grouping, Some((',', 3)));
        assert_eq!(spec.precision, Some(3));
        assert_eq!(spec.ty, 'e');
        let spec = FormatSpec::parse("_x", ValueKind::Int).unwrap();
        assert_eq!(spec.grouping, Some(('_', 4)));
        let spec = FormatSpec::parse(".6_f", ValueKind::Int).unwrap();
        assert_eq!(spec.frac_grouping, Some('_'));
        let spec = FormatSpec::parse("", ValueKind::Str).unwrap();
        assert_eq!(spec.ty, 's');
        let spec = FormatSpec::parse("", ValueKind::Int).unwrap();
        assert_eq!(spec.ty, 'd');
    }

    #[test]
    fn parse_errors_match_python() {
        let cases: &[(&str, ValueKind, &str)] = &[
            (
                "d",
                ValueKind::Str,
                "Unknown format code 'd' for object of type 'str'",
            ),
            (
                "s",
                ValueKind::Int,
                "Unknown format code 's' for object of type 'int'",
            ),
            (
                "=5",
                ValueKind::Str,
                "'=' alignment not allowed in string format specifier",
            ),
            (
                "+",
                ValueKind::Str,
                "Sign not allowed in string format specifier",
            ),
            (
                "-",
                ValueKind::Str,
                "Sign not allowed in string format specifier",
            ),
            (
                " 5",
                ValueKind::Str,
                "Space not allowed in string format specifier",
            ),
            (
                "#",
                ValueKind::Str,
                "Alternate form (#) not allowed in string format specifier",
            ),
            (
                "z",
                ValueKind::Str,
                "Negative zero coercion (z) not allowed in string format specifier",
            ),
            (",", ValueKind::Str, "Cannot specify ',' with 's'."),
            ("_", ValueKind::Str, "Cannot specify '_' with 's'."),
            (
                "abc",
                ValueKind::Str,
                "Invalid format specifier 'abc' for object of type 'str'",
            ),
            (
                ".2d",
                ValueKind::Int,
                "Precision not allowed in integer format specifier",
            ),
            (",x", ValueKind::Int, "Cannot specify ',' with 'x'."),
            (",_", ValueKind::Int, "Cannot specify both ',' and '_'."),
            ("_,", ValueKind::Int, "Cannot specify both ',' and '_'."),
            (",,", ValueKind::Int, "Cannot specify ',' with ','."),
            ("_n", ValueKind::Int, "Cannot specify '_' with 'n'."),
            (
                "+c",
                ValueKind::Int,
                "Sign not allowed with integer format specifier 'c'",
            ),
            (
                "#c",
                ValueKind::Int,
                "Alternate form (#) not allowed with integer format specifier 'c'",
            ),
            (
                "zd",
                ValueKind::Int,
                "Negative zero coercion (z) not allowed in integer format specifier",
            ),
            (".", ValueKind::Int, "Format specifier missing precision"),
            (".s", ValueKind::Str, "Format specifier missing precision"),
            (
                "99999999999999999999",
                ValueKind::Int,
                "Too many decimal digits in format string",
            ),
            (
                "{",
                ValueKind::Int,
                "Unknown format code '{' for object of type 'int'",
            ),
            (
                "\u{7}",
                ValueKind::Str,
                "Unknown format code '\\x7' for object of type 'str'",
            ),
        ];
        for (spec, kind, message) in cases {
            assert_eq!(
                FormatSpec::parse(spec, *kind).unwrap_err(),
                *message,
                "spec {spec:?}"
            );
        }
    }

    #[test]
    fn str_layout() {
        assert_eq!(fmt_str("INFO", " <8").unwrap(), "INFO    ");
        assert_eq!(fmt_str("INFO", ">8").unwrap(), "    INFO");
        assert_eq!(fmt_str("INFO", "^9").unwrap(), "  INFO   ");
        assert_eq!(fmt_str("INFO", "*^9").unwrap(), "**INFO***");
        assert_eq!(fmt_str("ab", "05").unwrap(), "ab000");
        assert_eq!(fmt_str("abcdef", ".3").unwrap(), "abc");
        assert_eq!(fmt_str("abcdef", ">5.2s").unwrap(), "   ab");
        assert_eq!(fmt_str("toolong", "<3").unwrap(), "toolong");
        // Width counts code points, not bytes or display columns
        assert_eq!(fmt_str("é😀", "*^7").unwrap(), "**é😀***");
        assert_eq!(fmt_str("日本語", ">5").unwrap(), "  日本語");
        assert_eq!(fmt_str("日本語", ".2").unwrap(), "日本");
        assert_eq!(fmt_str("x", "é>3").unwrap(), "ééx");
    }

    #[test]
    fn int_layout() {
        assert_eq!(fmt_int(42, "05d").unwrap(), "00042");
        assert_eq!(fmt_int(42, ">5").unwrap(), "   42");
        assert_eq!(fmt_int(42, "<5").unwrap(), "42   ");
        assert_eq!(fmt_int(42, "^6").unwrap(), "  42  ");
        assert_eq!(fmt_int(42, "+").unwrap(), "+42");
        assert_eq!(fmt_int(42, " ").unwrap(), " 42");
        assert_eq!(fmt_int(12, "=+08,d").unwrap(), "+000,012");
        assert_eq!(fmt_int(1_234_567, ",").unwrap(), "1,234,567");
        assert_eq!(fmt_int(1_234_567, "_").unwrap(), "1_234_567");
        assert_eq!(fmt_int(1234, "010,").unwrap(), "00,001,234");
        assert_eq!(fmt_int(1234, "09,d").unwrap(), "0,001,234");
        assert_eq!(fmt_int(1234, "012,").unwrap(), "0,000,001,234");
        assert_eq!(fmt_int(1234, "011_x").unwrap(), "0_0000_04d2");
        assert_eq!(fmt_int(12_345_678, "_x").unwrap(), "bc_614e");
        assert_eq!(fmt_int(12_345_678, "#_o").unwrap(), "0o5706_0516");
        assert_eq!(fmt_int(255, "#X").unwrap(), "0XFF");
        assert_eq!(fmt_int(255, "#010x").unwrap(), "0x000000ff");
        assert_eq!(fmt_int(5, "#b").unwrap(), "0b101");
        assert_eq!(fmt_int(65, "c").unwrap(), "A");
        assert_eq!(fmt_int(65, "05c").unwrap(), "0000A");
        assert_eq!(fmt_int(65, "^5c").unwrap(), "  A  ");
        assert_eq!(fmt_int(12, "n").unwrap(), "12");
        assert_eq!(fmt_int(12, "0=5").unwrap(), "00012");
        assert_eq!(fmt_int(12, "^=5").unwrap(), "^^^12");
        assert_eq!(fmt_int(12, "x^5,").unwrap(), "x12xx");
        assert_eq!(fmt_int(12, "05_").unwrap(), "0_012");
        let mut out = String::new();
        let spec = FormatSpec::parse("c", ValueKind::Int).unwrap();
        assert!(!spec.write_uint(&mut out, 0x11_0000));
        assert!(!spec.write_uint(&mut out, 0xD800));
        assert!(out.is_empty());
    }

    #[test]
    fn int_as_float() {
        assert_eq!(fmt_int(5, "f").unwrap(), "5.000000");
        assert_eq!(fmt_int(5, ",.2f").unwrap(), "5.00");
        assert_eq!(fmt_int(1_234_567, ",f").unwrap(), "1,234,567.000000");
        assert_eq!(fmt_int(1_234_567, "_f").unwrap(), "1_234_567.000000");
        assert_eq!(fmt_int(0, "#.0f").unwrap(), "0.");
        assert_eq!(fmt_int(1234, ".0f").unwrap(), "1234");
        assert_eq!(fmt_int(12, "F").unwrap(), "12.000000");
        assert_eq!(fmt_int(5, "e").unwrap(), "5.000000e+00");
        assert_eq!(fmt_int(123_456, ".3e").unwrap(), "1.235e+05");
        assert_eq!(fmt_int(12, "E").unwrap(), "1.200000E+01");
        assert_eq!(fmt_int(0, "#.0e").unwrap(), "0.e+00");
        assert_eq!(fmt_int(123, ".0e").unwrap(), "1e+02");
        assert_eq!(fmt_int(1_234_567, ",e").unwrap(), "1.234567e+06");
        // Ties round to even
        assert_eq!(fmt_int(125, ".1e").unwrap(), "1.2e+02");
        assert_eq!(fmt_int(135, ".1e").unwrap(), "1.4e+02");
        assert_eq!(fmt_int(1251, ".1e").unwrap(), "1.3e+03");
        assert_eq!(fmt_int(999_999, ".2e").unwrap(), "1.00e+06");
        assert_eq!(fmt_int(u64::MAX, "e").unwrap(), "1.844674e+19");
        assert_eq!(fmt_int(5, "%").unwrap(), "500.000000%");
        assert_eq!(fmt_int(5, ".2%").unwrap(), "500.00%");
        assert_eq!(fmt_int(12, "#.0%").unwrap(), "1200.%");
        assert_eq!(fmt_int(123_456_789, "g").unwrap(), "1.23457e+08");
        assert_eq!(fmt_int(1_234_567, ".3g").unwrap(), "1.23e+06");
        assert_eq!(fmt_int(10_000_000_000_000_000, "g").unwrap(), "1e+16");
        assert_eq!(fmt_int(12, "#g").unwrap(), "12.0000");
        assert_eq!(fmt_int(100, "#.3g").unwrap(), "100.");
        assert_eq!(fmt_int(12, "#.0g").unwrap(), "1.e+01");
        assert_eq!(fmt_int(123, ".0g").unwrap(), "1e+02");
        assert_eq!(fmt_int(12, "G").unwrap(), "12");
        assert_eq!(fmt_int(0, "g").unwrap(), "0");
        assert_eq!(fmt_int(999_999, "g").unwrap(), "999999");
        assert_eq!(fmt_int(9_999_999, "g").unwrap(), "1e+07");
        assert_eq!(fmt_int(123_456_789_012, ".15g").unwrap(), "123456789012");
        assert_eq!(fmt_int(1_234_567, "#.9_g").unwrap(), "1234567.00");
        // 3.14 fractional grouping
        assert_eq!(fmt_int(12, ".,f").unwrap(), "12.000,000");
        assert_eq!(fmt_int(1234, "015.5_f").unwrap(), "00001234.000_00");
        assert_eq!(fmt_int(1234, "016,.5_f").unwrap(), "0,001,234.000_00");
        assert_eq!(fmt_int(12, ".,d").unwrap(), "12");
    }
}
