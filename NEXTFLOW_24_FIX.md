# Fix for Nextflow 24.04.2

The first starter used this pattern:

```groovy
checked = CHECK_INPUT(input_ch)
profiled = PROFILE_FAIRE(checked.out.workbook)
```

On Nextflow 24.04.2, `checked` is already a `ChannelOut`, so asking for
`checked.out` causes:

```text
No such property: out for class: groovyx.gpars.dataflow.DataflowBroadcast
```

The corrected workflow invokes each process once and accesses named emitted
outputs through the process output namespace:

```groovy
CHECK_INPUT(input_ch)
PROFILE_FAIRE(CHECK_INPUT.out.workbook)
CHECK_STAGE(PROFILE_FAIRE.out.profile)

PACKAGE_RESULTS(
    CHECK_INPUT.out.workbook,
    PROFILE_FAIRE.out.profile,
    CHECK_STAGE.out.report,
    CHECK_STAGE.out.summary
)
```

This form is clearer and compatible with the installed Nextflow 24.04.2 setup.
