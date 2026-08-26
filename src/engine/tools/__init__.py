"""Scientific primitives shared across stages and gate families.

A tool is an ordinary class (or module) that takes sequences and returns facts. It has
no opinion about why it is being called — stages and gate families **use** one rather
than inheriting from it (docs/engine-design.md §5a).

Tools import nothing but ``engine.domain`` and their scientific library, which is what
makes each one testable with no pipeline around it.
"""
