# gef-pprint-register
gef extension to print register "prettier", including SIMD registers pretty-print and casting to primitive data types.

> **NOTE:**
>
> Make sure append `set print repeats 64` to your `.gdbinit` file, to fetch (up to zmm) registers. ~~Repeat count must be 128 or more, if you use 1024-bit or more registers XD~~

## Concepts
> Viewing specific register's bytes into format.
>
> Format example: `rez $ymm0[23:16]:u8`

## Indexing and slicing
Both slicing and indexing are available with the index of byte. 

Default endianess and slicing is Little endian, whole size of register.

### Indexing
Index are ordered with **Little Endian**. For example, `rez $ymm0[31]` will return the most significant byte of 256-bit (32-byte) `ymm` register.

### Slicing
You can explicitly give the endianess by 'start' and 'stop' of slice.
* `start < stop` will format by **Big Endian**.
* `start > stop` will format by **Little Endian**.

## Available Formats
Using larger bit type on smaller bit array might result in 

### Integer
* `u8`, `u16`, `u32` ... `u512`: format to unsigned decimal integer format. 
* `d8`, `d16`, `d32` ... `d512`: format to signed decimal integer format. 
* `b/o/x8`, `b/o/x16` ... `b/o/x512`: format to binary / octal / hexadecimal format.

### Floating points
* `f32`, `f64` are available, as `float` and `double`

### Character and Strings
* `c`: ASCII / ISO 8859-1 (Latin-1) size, by byte.