# Configuring a template - copier

## Configuration sources[¶](https://copier.readthedocs.io/en/stable/configuring/#configuration-sources "Permanent link")

It is important that you understand how Copier works. It has 2 kinds of
configurations:

1. **Settings** for Copier itself. This includes things as minimal Copier
    version required, which subdirectory to render, tasks to run, etc.
2. **Answers**. This is customized per template. The user answers template
    questions, and those answers are stored as variables available for the
    template at rendering time.

Copier reads **settings** from these sources, in this order of priority:

1. Command line or API arguments.
2. [The `copier.yml`
   file](https://copier.readthedocs.io/en/stable/configuring/#the-copieryml-file
   "The copier.yml file").
    Settings here always start with an underscore (e.g. `_min_copier_version`).

Info

Some settings are _only_ available as CLI arguments, and some others _only_ as
template configurations. Some behave differently depending on where they are
defined.
[Check the docs for each specific
setting](https://copier.readthedocs.io/en/stable/configuring/#available-settings
"Available settings").

Copier obtains **answers** from these sources, in this order of priority:

1. Command line or API arguments.
2. Asking the user. Notice that Copier will not ask any questions answered in
    the previous source.
3. [Answer from last
   execution](https://copier.readthedocs.io/en/stable/configuring/#the-copier-answersyml-file
   "The .copier-answers.yml file").
4. Default values defined in
    [the `copier.yml`
    file](https://copier.readthedocs.io/en/stable/configuring/#the-copieryml-file
    "The copier.yml file").

## The `copier.yml` file[¶](https://copier.readthedocs.io/en/stable/configuring/#the-copieryml-file "Permanent link")

The `copier.yml` (or `copier.yaml`) file is found in the root of the template,
and it is the main entrypoint for managing your template configuration. It will
be read and used for two purposes:

- [Prompting the user for
  information](https://copier.readthedocs.io/en/stable/configuring/#questions
  "Questions").
- [Applying template settings](https://copier.readthedocs.io/en/stable/configuring/#available-settings "Available settings")
    (excluding files, setting arguments defaults, etc.).

### Questions[¶](https://copier.readthedocs.io/en/stable/configuring/#questions "Permanent link")

For each key found, Copier will prompt the user to fill or confirm the values
before they become available to the project template.

Example

This `copier.yml` file:

```yaml
name_of_the_project: My awesome project
number_of_eels: 1234
your_email: ""

```

Will result in a questionnaire similar to:

```text
🎤 name_of_the_project
  My awesome project
🎤 number_of_eels (int)
  1234
🎤 your_email

```

#### Advanced prompt formatting[¶](https://copier.readthedocs.io/en/stable/configuring/#advanced-prompt-formatting "Permanent link")

Apart from the simplified format, as seen above, Copier supports a more
advanced format to ask users for data. To use it, the value must be a dict.

Supported keys:

- **type**: User input must match this type. Options are: `bool`, `float`,
    `int`, `json`, `str`, `yaml` (default).
- **help**: Additional text to help the user know what's this question for.
- **choices**: To restrict possible values.

    Tip

    A choice value of `null` makes it become the same as its key.

    Validation and conditional choices

    A choice can be validated by using the extended syntax with dict-style and
    tuple-style choices. For example:

    ```copier.yml
    cloud:
        type: str
        help: Which cloud provider do you use?
        choices:
            - Any
            - AWS
            - Azure
            - GCP
    
    iac:
        type: str
        help: Which IaC tool do you use?
        choices:
            Terraform: tf
            Cloud Formation:
                value: cf
                validator: "{% if cloud != 'AWS' %}Requires AWS{% endif %}"
            Azure Resource Manager:
                value: arm
                validator: "{% if cloud != 'Azure' %}Requires Azure{% endif %}"
            Deployment Manager:
                value: dm
                validator: "{% if cloud != 'GCP' %}Requires GCP{% endif %}"
    
    ```

    When the rendered validator is a non-empty string, the choice is disabled
    and the message is shown. Choice validation is useful when the validity of a
    choice depends on the answer to a previous question.

    Dynamic choices

    Choices can be created dynamically by using a templated string which renders
    as valid list-style, dict-style, or tuple-style choices in YAML format. For
    example:

    ```copier.yml
    language:
        type: str
        help: Which programming language do you use?
        choices:
            - python
            - node
    
    dependency_manager:
        type: str
        help: Which dependency manager do you use?
        choices: |
            {%- if language == "python" %}
            - poetry
            - pipenv
            {%- else %}
            - npm
            - yarn
            {%- endif %}
    
    ```

    Dynamic choices can be used as an alternative approach to conditional
    choices via validators where dynamic choices hide disabled choices whereas
    choices disabled via validators are visible with along with the validator's
    error message but cannot be selected.

    When combining dynamic choices with validators, make sure to escape the
    validator template using `{% raw %}...{% endraw %}`.

    Warning

    You are able to use different types for each choice value, but it is not
    recommended because you can get to some weird scenarios.

    For example, try to understand this 🥴

    ```copier.yml
    pick_one:
        type: yaml # If you are mixing types, better be explicit
        choices:
            Nothing, thanks: "null" # Will be YAML-parsed and converted to null
            Value is key: null # Value will be converted to "Value is key"
            One and a half: 1.5
            "Yes": true
            Nope: no
            Some array: "[yaml, converts, this]"
    
    ```

    It's better to stick with a simple type and reason about it later in
    template code:

    ```copier.yml
    pick_one:
        type: str
        choices:
            Nothing, thanks: ""
            Value is key: null # Becomes "Value is key", which is a str
            One and a half: "1.5"
            "Yes": "true"
            Nope: "no"
            Some array: "[str, keeps, this, as, a, str]"
    
    ```

- **multiselect**: When set to `true`, allows multiple choices. The answer
    will be a `list[T]` instead of a `T` where `T` is of type `type`.

- **default**: Leave empty to force the user to answer. Provide a default to
    save them from typing it if it's quite common. When using `choices`, the
    default must be the choice _value_, not its _key_, and it must match its
    _type_. If values are quite long, you can use
    [YAML anchors](https://confluence.atlassian.com/bitbucket/yaml-anchors-960154027.html).
- **secret**: When `true`, it hides the prompt displaying asterisks (`*****`)
    and doesn't save the answer in
    [the answers
    file](https://copier.readthedocs.io/en/stable/configuring/#the-copier-answersyml-file
    "The .copier-answers.yml file").
    When `true`, a default value is required.
- **placeholder**: To provide a visual example for what would be a good
    value. It is only shown while the answer is empty, so maybe it doesn't make
    much sense to provide both `default` and `placeholder`. It must be a string.

    Warning

    Multiline placeholders are not supported currently, due to [this upstream bug](https://github.com/prompt-toolkit/python-prompt-toolkit/issues/1267).

- **multiline**: When set to `true`, it allows multiline input. This is
    especially useful when `type` is `json` or `yaml`.

- **validator**: Jinja template with which to validate the user input. This
    template will be rendered with the combined answers as variables; it should
    render _nothing_ if the value is valid, and an error message to show to the
    user otherwise.

- **when**: Condition that, if `false`, skips the question.

    If it is a boolean, it is used directly. Setting it to `false` is useful for
    creating a computed value.

    If it is a string, it is converted to boolean using a parser similar to
    YAML, but only for boolean values. The string can be
    [templated](https://copier.readthedocs.io/en/stable/configuring/#prompt-templating
    "Prompt templating").

    If a question is skipped, its answer is not recorded, but its default value
    is available in the render context.

    Example

    ```copier.yaml
    project_creator:
        type: str
    
    project_license:
        type: str
        choices:
            - GPLv3
            - Public domain
    
    copyright_holder:
        type: str
        default: |-
            {% if project_license == 'Public domain' -%}
                {#- Nobody owns public projects -#}
                nobody
            {%- else -%}
                {#- By default, project creator is the owner -#}
                {{ project_creator }}
            {%- endif %}
        # Only ask for copyright if project is not in the public domain
        when: "{{ project_license != 'Public domain' }}"
    
    ```

Example

```copier.yml
love_copier:
    type: bool # This makes Copier ask for y/n
    help: Do you love Copier?
    default: yes # Without a default, you force the user to answer

project_name:
    type: str # Any value will be treated raw as a string
    help: An awesome project needs an awesome name. Tell me yours.
    default: paradox-specifier
    validator: >-
        {% if not (project_name | regex_search('^[a-z][a-z0-9\-]+$')) %}
        project_name must start with a letter, followed one or more letters, digits or dashes all lowercase.
        {% endif %}

rocket_launch_password:
    type: str
    secret: true # This value will not be logged into .copier-answers.yml
    placeholder: my top secret password

# I'll avoid default and help here, but you can use them too
age:
    type: int
    validator: "{% if age <= 0 %}Must be positive{% endif %}"

height:
    type: float

any_json:
    help: Tell me anything, but format it as a one-line JSON string
    type: json
    multiline: true

any_yaml:
    help: Tell me anything, but format it as a one-line YAML string
    type: yaml # This is the default type, also for short syntax questions
    multiline: true

your_favorite_book:
    # User will choose one of these and your template will get the value
    choices:
        - The Bible
        - The Hitchhiker's Guide to the Galaxy

project_license:
    # User will see only the dict key and choose one, but you will
    # get the dict value in your template
    choices:
        MIT: &mit_text |
            Here I can write the full text of the MIT license.
            This will be a long text, shortened here for example purposes.
        Apache2: |
            Full text of Apache2 license.
    # When using choices, the default value is the value, **not** the key;
    # that's why I'm using the YAML anchor declared above to avoid retyping the
    # whole license
    default: *mit_text
    # You can still define the type, to make sure answers that come from --data
    # CLI argument match the type that your template expects
    type: str

close_to_work:
    help: Do you live close to your work?
    # This format works just like the dict one
    choices:
        - [at home, I work at home]
        - [less than 10km, quite close]
        - [more than 10km, not so close]
        - [more than 100km, quite far away]

```

#### Prompt templating[¶](https://copier.readthedocs.io/en/stable/configuring/#prompt-templating "Permanent link")

Most of those options can be templated using Jinja.

Keep in mind that the configuration is loaded as **YAML**, so the contents must
be **valid YAML** and respect **Copier's structure**. That is why we explicitly
wrap some strings in double-quotes in the following examples.

Answers provided through interactive prompting will not be rendered with Jinja,
so you cannot use Jinja templating in your answers.

Example

```copier.yml
# default
username:
    type: str

organization:
    type: str

email:
    type: str
    # Notice that both `username` and `organization` have been already asked
    default: "{{ username }}@{{ organization }}.com"

# help
copyright_holder:
    type: str
    when: "{% if organization != 'Public domain' %}true{% endif %}"
    help: The person or entity within {{ organization }} that holds copyrights.

# type
target:
    type: str
    choices:
        - humans
        - machines

user_config:
    type: "{% if target == 'humans' %}yaml{% else %}json{% endif %}"

# choices
title:
    type: str
    help: Your title within {{ organization }}

contact:
    choices:
        Copyright holder: "{{ copyright_holder }}"
        CEO: Alice Bob
        CTO: Carl Dave
        "{{ title }}": "{{ username }}"

```

Warning

Keep in mind that:

1. You can only template inside the value…
2. … which must be a string to be templated.
3. Also you won't be able to use variables that aren't yet declared.

```copier.yml
your_age:
    type: int

# Valid
double_it:
    type: int
    default: "{{ your_age * 2}}"

# Invalid, the templating occurs outside of the parameter value
did_you_ask:
    type: str
    {% if your_age %}
    default: "yes"
    {% else %}
    placeholder: "nope"
    {% endif %}

# Invalid, `a_random_word` wasn't answered yet
other_random_word:
    type: str
    placeholder: "Something different to {{ a_random_word }}"

# Invalid, YAML interprets curly braces
a_random_word:
    type: str
    default: {{ 'hello' }}

```

### Include other YAML files[¶](https://copier.readthedocs.io/en/stable/configuring/#include-other-yaml-files "Permanent link")

The `copier.yml` file supports multiple documents as well as using the
`!include` tag to include settings and questions from other YAML files. This
allows you to split up a larger `copier.yml` and enables you to reuse common
partial sections from your templates. When multiple documents are used, care
has to be taken with questions and settings that are defined in more than one
document:

- A question with the same name overwrites definitions from an earlier
    document.
- Settings given in multiple documents for `exclude`, `skip_if_exists`,
    `jinja_extensions` and `secret_questions` are concatenated.
- Other settings (such as `tasks` or `migrations`) overwrite previous
    definitions for these settings.

Hint

You can use
[Git submodules](https://git-scm.com/book/en/v2/Git-Tools-Submodules) to sanely
include shared code into templates.

Example

This would be a valid `copier.yml` file:

```copier.yml
---
# Copier will load all these files
!include shared-conf/common.*.yml

# These 3 lines split the several YAML documents
---
# These two documents include common questions for these kind of projects
!include common-questions/web-app.yml
---
!include common-questions/python-project.yml
---

# Here you can specify any settings or questions specific for your template
_skip_if_exists:
    - .password.txt
custom_question: default answer

```

that includes questions and settings from:

common-questions/python-project.yml

```yaml
version:
    type: str
    help: What is the version of your Python project?

# Settings like `_skip_if_exists` are merged
_skip_if_exists:
    - "pyproject.toml"

```

## Conditional files and directories[¶](https://copier.readthedocs.io/en/stable/configuring/#conditional-files-and-directories "Permanent link")

You can take advantage of the ability to template file and directory names to
make them "conditional", i.e. to only generate them based on the answers given
by a user.

For example, you can ask users if they want to use
[pre-commit](https://pre-commit.com/):

```copier.yml
use_precommit:
    type: bool
    default: false
    help: Do you want to use pre-commit?

```

And then, you can generate a `.pre-commit-config.yaml` file only if they
answered "yes":

```text
📁 your_template
├── 📄 copier.yml
└── 📄 {% if use_precommit %}.pre-commit-config.yaml{% endif %}.jinja

```

Important

Note that the chosen
[template suffix](https://copier.readthedocs.io/en/stable/configuring/#templates_suffix "templates_suffix")
**must** appear outside of the Jinja condition, otherwise the whole file won't
be considered a template and will be copied as such in generated projects.

You can even use the answers of questions with
[choices](https://copier.readthedocs.io/en/stable/configuring/#advanced-prompt-formatting
"Advanced prompt formatting"):

```copier.yml
ci:
    type: str
    help: What Continuous Integration service do you want to use?
    choices:
        GitHub CI: github
        GitLab CI: gitlab
    default: github

```

```text
📁 your_template
├── 📄 copier.yml
├── 📁 {% if ci == 'github' %}.github{% endif %}
│   └── 📁 workflows
│       └── 📄 ci.yml
└── 📄 {% if ci == 'gitlab' %}.gitlab-ci.yml{% endif %}.jinja

```

Important

Contrary to files, directories **must not** end with the
[template
suffix](https://copier.readthedocs.io/en/stable/configuring/#templates_suffix
"templates_suffix").

Warning

On Windows, double-quotes are not valid characters in file and directory paths.
This is why we used **single-quotes** in the example above.

## Generating a directory structure[¶](https://copier.readthedocs.io/en/stable/configuring/#generating-a-directory-structure "Permanent link")

You can use answers to generate file names as well as whole directory
structures.

```copier.yml
package:
    type: str
    help: Package name

```

```text
📁 your_template
├── 📄 copier.yml
└── 📄 {{ package.replace('.', _copier_conf.sep) }}{{ _copier_conf.sep }}__main__.py.jinja

```

If you answer

> your\_package.cli.main

Copier will generate this structure:

```text
📁 your_project
└── 📁 your_package
    └── 📁 cli
        └── 📁 main
            └── 📄 __main__.py

```

You can either use any separator, like `.`, and replace it with
`_copier_conf.sep`, like in the example above, or just use `/` in the answer
(works on Windows too).

## Importing Jinja templates and macros[¶](https://copier.readthedocs.io/en/stable/configuring/#importing-jinja-templates-and-macros "Permanent link")

You can
[include templates](https://jinja.palletsprojects.com/en/3.1.x/templates/#include)
and
[import macros](https://jinja.palletsprojects.com/en/3.1.x/templates/#import)
to reduce code duplication. A common scenario is the derivation of new values
from answers, e.g. computing the slug of a human-readable name:

```copier.yml
_exclude:
    - name-slug

name:
    type: str
    help: A nice human-readable name

slug:
    type: str
    help: A slug of the name
    default: "{% include 'name-slug.jinja' %}"

```

```name-slug.jinja
{# For simplicity ... -#}
{{ name|lower|replace(' ', '-') }}

```

```text
📁 your_template
├── 📄 copier.yml
└── 📄 name-slug.jinja

```

It is also possible to include a template in a templated folder name

```text
📁 your_template
├── 📄 copier.yml
├── 📄 name-slug.jinja
└── 📁 {% include 'name-slug.jinja' %}
    └── 📄 __init__.py

```

or in a templated file name

```text
📁 your_template
├── 📄 copier.yml
├── 📄 name-slug.jinja
└── 📄 {% include 'name-slug.jinja' %}.py

```

or in the templated content of a text file:

```pyproject.toml.jinja
[project]
name = "{% include 'name-slug.jinja' %}"
# ...

```

Similarly, a Jinja macro can be defined

```slugify.jinja
{# For simplicity ... -#}
{% macro slugify(value) -%}
{{ value|lower|replace(' ', '-') }}
{%- endmacro %}

```

and imported, e.g. in `copier.yml`

```copier.yml
_exclude:
    - slugify

name:
    type: str
    help: A nice human-readable name

slug:
    type: str
    help: A slug of the name
    default: "{% from 'slugify.jinja' import slugify %}{{ slugify(name) }}"

```

or in a templated folder name, in a templated file name, or in the templated
content of a text file.

Info

Import/Include paths are relative to the template root.

As the number of imported templates and macros grows, you may want to place
them in a dedicated folder such as `includes`:

```text
📁 your_template
├── 📄 copier.yml
└── 📁 includes
    ├── 📄 name-slug.jinja
    ├── 📄 slugify.jinja
    └── 📄 ...

```

Then, make sure to
[exclude](https://copier.readthedocs.io/en/stable/configuring/#exclude) this
folder

```copier.yml
_exclude:
    - includes

```

or use a
[subdirectory](https://copier.readthedocs.io/en/stable/configuring/#subdirectory),
e.g.:

```copier.yml
_subdirectory: template

```

In addition, Jinja include and import statements will need to use a POSIX path
separator (also on Windows) which is not supported in templated folder and file
names. For this reason, Copier provides a function
`pathjoin(*paths: str, mode: Literal["posix", "windows", "native"] = "posix")`:

```jinja
{% include pathjoin('includes', 'name-slug.jinja') %}

```

```jinja
{% from pathjoin('includes', 'slugify.jinja') import slugify %}

```

## Available settings[¶](https://copier.readthedocs.io/en/stable/configuring/#available-settings "Permanent link")

Template settings alter how the template is rendered.
[They come from several
sources](https://copier.readthedocs.io/en/stable/configuring/#configuration-sources
"Configuration sources").

Remember that **the key must be prefixed with an underscore if you use it in
[the `copier.yml` file](https://copier.readthedocs.io/en/stable/configuring/#the-copieryml-file "The copier.yml file")
**.

### `answers_file`[¶](https://copier.readthedocs.io/en/stable/configuring/#answers_file "Permanent link")

- Format: `str`
- CLI flags: `-a`, `--answers-file`
- Default value: `.copier-answers.yml`

Path to a file where answers will be recorded by default. The path must be
relative to the project root.

Tip

Remember to add that file to your Git template if you want to support
[updates](https://copier.readthedocs.io/en/stable/updating/).

Don't forget to read
[the docs about the answers
file](https://copier.readthedocs.io/en/stable/configuring/#the-copier-answersyml-file
"The .copier-answers.yml file").

Example

```copier.yml
_answers_file: .my-custom-answers.yml

```

### `cleanup_on_error`[¶](https://copier.readthedocs.io/en/stable/configuring/#cleanup_on_error "Permanent link")

- Format: `bool`
- CLI flags: `-C`, `--no-cleanup` (used to disable this setting; only
    available in `copier copy` subcommand)
- Default value: `True`

When Copier creates the destination path, if there's any failure when rendering
the template (either in the rendering process or when running the
[tasks](https://copier.readthedocs.io/en/stable/configuring/#tasks)), Copier
will delete that folder.

Copier will never delete the folder if it didn't create it. For this reason,
when running `copier update`, this setting has no effect.

Info

Not supported in `copier.yml`.

### `conflict`[¶](https://copier.readthedocs.io/en/stable/configuring/#conflict "Permanent link")

- Format: `Literal["rej", "inline"]`
- CLI flags: `-o`, `--conflict` (only available in `copier update` subcommand)
- Default value: `inline`

When updating a project, sometimes Copier doesn't know what to do with a diff
code hunk. This option controls the output format if this happens. Using `rej`,
creates `*.rej` files that contain the unresolved diffs. The `inline` option
(default) includes the diff code hunk in the file itself, similar to the
behaviour of `git merge`.

Info

Not supported in `copier.yml`.

### `context_lines`[¶](https://copier.readthedocs.io/en/stable/configuring/#context_lines "Permanent link")

- Format: `Int`
- CLI flags: `-c`, `--context-lines` (only available in `copier update`
    subcommand)
- Default value: `1`

During a project update, Copier needs to compare the template evolution with
the subproject evolution. This way, it can detect what changed, where and how
to merge those changes.
[Refer here for more details on this process](https://copier.readthedocs.io/en/stable/updating/).

The more lines you use, the more accurate Copier will be when detecting
conflicts. But you will also have more conflicts to solve by yourself. FWIW,
Git uses 3 lines by default.

The less lines you use, the less conflicts you will have. However, Copier will
not be so accurate and could even move lines around if the file it's comparing
has several similar code chunks.

Info

Not supported in `copier.yml`.

### `data`[¶](https://copier.readthedocs.io/en/stable/configuring/#data "Permanent link")

- Format: `dict|List[str=str]`
- CLI flags: `-d`, `--data`
- Default value: N/A

Give answers to questions through CLI/API.

This cannot be defined in `copier.yml`, where its equivalent would be just
normal questions with default answers.

Example

Example CLI usage to take all default answers from template, except the user
name, which is overridden, and don't ask user anything else:

```bash
copier copy -fd 'user_name=Manuel Calavera' template destination

```

### `data_file`[¶](https://copier.readthedocs.io/en/stable/configuring/#data_file "Permanent link")

- Format: `str`
- CLI flags: `--data-file`
- Default value: N/A

As an alternative to
[`-d, --data`](https://copier.readthedocs.io/en/stable/configuring/#data) you
can also pass the path to a YAML file that contains your data.

Info

Not supported in `copier.yml` or API calls. Only supported through the CLI.

Example

Example CLI usage with a YAML file containing data:

```input.yml
user_name: Manuel Calavera
age: 7
height: 1.83

```

Passing a data file

```bash
copier copy --data-file input.yml template destination

```

is equivalent to passing its content as key-value pairs:

```bash
copier copy -d 'user_name=Manuel Calavera' -d 'age=7' -d 'height=1.83' template destination

```

If you'd like to override some of the answers in the file, `--data` flags
always take precedence:

```bash
copier copy -d 'user_name=Bilbo Baggins' --data-file input.yml template destination

```

Info

Command line arguments passed via `--data` always take precedence over the data
file.

### `external_data`[¶](https://copier.readthedocs.io/en/stable/configuring/#external_data "Permanent link")

- Format: `dict[str, str]`
- CLI flags: N/A
- Default value: `{}`

This allows using preexisting data inside the rendering context. The format is
a dict of strings, where:

- The dict key will be the namespace of the data under
    [`_external_data`](https://copier.readthedocs.io/en/stable/creating/#_external_data).
- The dict value is the relative path (from the subproject destination) where
    the YAML data file should be found.

Template composition

If your template is
[a complement of another
template](https://copier.readthedocs.io/en/stable/configuring/#applying-multiple-templates-to-the-same-subproject
"Applying multiple templates to the same subproject"),
you can access the other template's answers with a pattern similar to this:

```copier.yml
# Child template defaults to a different answers file, to avoid conflicts
_answers_file: .copier-answers.child-tpl.yml

# Child template loads parent answers
_external_data:
    # A dynamic path. Make sure you answer that question
    # before the first access to the data (with `_external_data.parent_tpl`)
    parent_tpl: "{{ parent_tpl_answers_file }}"

# Ask user where they stored parent answers
parent_tpl_answers_file:
    help: Where did you store answers of the parent template?
    default: .copier-answers.yml

# Use a parent answer as the default value for a child question
target_version:
    help: What version are you deploying?
    # We already answered the `parent_tpl_answers_file` question, so we can
    # now correctly access the external data from `_external_data.parent_tpl`
    default: "{{ _external_data.parent_tpl.target_version }}"

```

Loading secrets

If your template has
[secret
questions](https://copier.readthedocs.io/en/stable/configuring/#secret_questions
"secret_questions"),
you can load the secrets and use them, e.g., as default answers with a pattern
similar to this:

```yaml
# Template loads secrets from Git-ignored file
_external_data:
    # A static path. If missing, it will return an empty dict
    secrets: .secrets.yaml

# Use a secret answers as the default value for a secret question
password:
    help: What is the password?
    secret: true
    # If `.secrets.yaml` exists, it has been loaded at this point and we can
    # now correctly access the external data from `_external_data.secrets`
    default: "{{ _external_data.secrets.password }}"

```

A template might even render `.secrets.yaml` with the answers to secret
questions similar to this:

```.secrets.yaml.jinja
password: "{{ password }}"

```

### `envops`[¶](https://copier.readthedocs.io/en/stable/configuring/#envops "Permanent link")

- Format: `dict`
- CLI flags: N/A
- Default value: `{"keep_trailing_newline": true}`

Configurations for the Jinja environment. Copier uses the Jinja defaults
whenever possible. The only exception at the moment is that
[Copier keeps trailing newlines](https://github.com/copier-org/copier/issues/464)
at the end of a template file. If you want to remove those, either remove them
from the template or set `keep_trailing_newline` to `false`.

See
[upstream docs](https://jinja.palletsprojects.com/en/3.1.x/api/#jinja2.Environment)
to know available options.

Warning

Copier 5 and older had different, bracket-based defaults.

If your template was created for Copier 5, you need to add this configuration
to your `copier.yaml` to keep it working just like before:

```yaml
_envops:
    autoescape: false
    block_end_string: "%]"
    block_start_string: "[%"
    comment_end_string: "#]"
    comment_start_string: "[#"
    keep_trailing_newline: true
    variable_end_string: "]]"
    variable_start_string: "[["

```

By specifying this, your template will be compatible with both Copier 5 and 6.

Copier 6 will apply these older defaults if your
[min\_copier\_version](https://copier.readthedocs.io/en/stable/configuring/#min_copier_version)
is lower than 6.

Copier 7+ no longer uses the old defaults independent of
[min\_copier\_version](https://copier.readthedocs.io/en/stable/configuring/#min_copier_version).

### `exclude`[¶](https://copier.readthedocs.io/en/stable/configuring/#exclude "Permanent link")

- Format: `List[str]`
- CLI flags: `-x`, `--exclude`
- Default value:
    `["copier.yaml", "copier.yml", "~*", "*.py[co]", "__pycache__", ".git",
    ".DS_Store", ".svn"]`

[Patterns](https://copier.readthedocs.io/en/stable/configuring/#patterns-syntax "Patterns syntax")
for files/folders that must not be copied.

The CLI option can be passed several times to add several patterns.

Each pattern can be templated using Jinja.

Example

Templating `exclude` patterns using `_copier_operation` allows to have files
that are rendered once during `copy`, but are never updated:

```yaml
_exclude:
    - "{% if _copier_operation == 'update' -%}src/*_example.py{% endif %}"

```

The difference with
[skip\_if\_exists](https://copier.readthedocs.io/en/stable/configuring/#skip_if_exists)
is that it will never be rendered during an update, no matter if it exists or
not.

Info

When you define this parameter in `copier.yml`, it will **replace** the default
value.

In this example, for instance, `"copier.yml"` will **not** be excluded:

```example
_exclude:
    - "*.bar"
    - ".git"

```

Info

When the
[`subdirectory`](https://copier.readthedocs.io/en/stable/configuring/#subdirectory)
parameter is defined and its value is the path of an actual subdirectory (i.e.
not `""` or `"."` or `"./"`), then the default value of the `exclude` parameter
is `[]`.

Info

When you add this parameter from CLI or API, it will **not replace** the values
defined in `copier.yml` (or the defaults, if missing).

Instead, CLI/API definitions **will extend** those from `copier.yml`.

Example CLI usage to copy only a single file from the template

```bash
copier copy --exclude '*' --exclude '!file-i-want' ./template ./destination

```

### `force`[¶](https://copier.readthedocs.io/en/stable/configuring/#force "Permanent link")

- Format: `bool`
- CLI flags: `-f`, `--force` (N/A in `copier update`)
- Default value: `False`

Overwrite files that already exist, without asking.

Also don't ask questions to the user; just use default values
[obtained from other
sources](https://copier.readthedocs.io/en/stable/configuring/#configuration-sources
"Configuration sources").

Info

Not supported in `copier.yml`.

### `defaults`[¶](https://copier.readthedocs.io/en/stable/configuring/#defaults "Permanent link")

- Format: `bool`
- CLI flags: `--defaults`
- Default value: `False`

Use default answers to questions.

Attention

Any question that does not have a default value must be answered
[via CLI/API](https://copier.readthedocs.io/en/stable/configuring/#data "data").
Otherwise, an error is raised.

Info

Not supported in `copier.yml`.

### `overwrite`[¶](https://copier.readthedocs.io/en/stable/configuring/#overwrite "Permanent link")

- Format: `bool`
- CLI flags: `--overwrite` (N/A in `copier update` because it's implicit)
- Default value: `False`

Overwrite files that already exist, without asking.

[obtained from other
sources](https://copier.readthedocs.io/en/stable/configuring/#configuration-sources
"Configuration sources").

Info

Not supported in `copier.yml`.

Required when updating from API.

### `jinja_extensions`[¶](https://copier.readthedocs.io/en/stable/configuring/#jinja_extensions "Permanent link")

- Format: `List[str]`
- CLI flags: N/A
- Default value: `[]`

Additional Jinja2 extensions to load in the Jinja2 environment. Extensions can
add filters, global variables and functions, or tags to the environment.

The following extensions are _always_ loaded:

- [`jinja2_ansible_filters.AnsibleCoreFiltersExtension`](https://gitlab.com/dreamer-labs/libraries/jinja2-ansible-filters/):
    this extension adds most of the
    [Ansible filters](https://docs.ansible.com/ansible/2.3/playbooks_filters.html)
    to the environment.

You don't need to tell your template users to install these extensions: Copier
depends on them, so they are always installed when Copier is installed.

Warning

Including an extension allows Copier to execute uncontrolled code, thus making
the template potentially more dangerous. Be careful about what extensions you
install.

Note to template writers

You must inform your users that they need to install the extensions alongside
Copier, i.e. in the same virtualenv where Copier is installed. For example, if
your template uses `jinja2_time.TimeExtension`, your users must install the
`jinja2-time` Python package.

```bash
# with pip, in the same virtualenv where Copier is installed
pip install jinja2-time

# if Copier was installed with pipx
pipx inject copier jinja2-time
# if Copier was installed with uv
uv tool install --with jinja2-time copier

```

Example

```copier.yml
_jinja_extensions:
    - jinja_markdown.MarkdownExtension
    - jinja2_slug.SlugExtension
    - jinja2_time.TimeExtension

```

Hint

Examples of extensions you can use:

- [Native Jinja2 extensions](https://jinja.palletsprojects.com/en/3.1.x/extensions/):

  - [expression statement](https://jinja.palletsprojects.com/en/3.1.x/templates/#expression-statement),
    which can be used to alter the Jinja context (answers, filters, etc.) or
    execute other operations, without outputting anything.
  - [loop controls](https://jinja.palletsprojects.com/en/3.1.x/extensions/#loop-controls),
    which adds the `break` and `continue` keywords for Jinja loops.
  - [debug extension](https://jinja.palletsprojects.com/en/3.1.x/extensions/#debug-extension),
    which can dump the current context thanks to the added `{% debug %}` tag.
- From [cookiecutter](https://cookiecutter.readthedocs.io/en/1.7.2/):

  - [`cookiecutter.extensions.JsonifyExtension`](https://cookiecutter.readthedocs.io/en/latest/advanced/template_extensions.html#jsonify-extension):
    provides a `jsonify` filter, to format a dictionary as JSON. Note that
    Copier natively provides a `to_nice_json` filter that can achieve the same
    thing.
  - [`cookiecutter.extensions.RandomStringExtension`](https://cookiecutter.readthedocs.io/en/latest/advanced/template_extensions.html#random-string-extension):
    provides a `random_ascii_string(length, punctuation=False)` global
    function. Note that Copier natively provides the `ans_random` and `hash`
    filters that can be used to achieve the same thing:

    ```example
    {{ 999999999999999999999999999999999|ans_random|hash('sha512') }}
    ```

  - [`cookiecutter.extensions.SlugifyExtension`](https://cookiecutter.readthedocs.io/en/latest/advanced/template_extensions.html#slugify-extension):
    provides a `slugify` filter using
    [python-slugify](https://github.com/un33k/python-slugify).

- [`copier_templates_extensions.TemplateExtensionLoader`](https://github.com/copier-org/copier-templates-extensions):
    enhances the extension loading mechanism to allow templates writers to put
    their extensions directly in their templates. It also allows to modify the
    rendering context (the Jinja variables that you can use in your templates)
    before rendering templates, see
    [using a context
    hook](https://copier.readthedocs.io/en/stable/faq/#how-can-i-alter-the-context-before-rendering-the-project
    "How can I alter the context before rendering the project?").

- [`jinja_markdown.MarkdownExtension`](https://github.com/jpsca/jinja-markdown):
    provides a `markdown` tag that will render Markdown to HTML using
    [PyMdown extensions](https://facelessuser.github.io/pymdown-extensions/).
- [`jinja2_slug.SlugExtension`](https://pypi.org/project/jinja2-slug/#files):
    provides a `slug` filter using
    [unicode-slugify](https://github.com/mozilla/unicode-slugify).
- [`jinja2_time.TimeExtension`](https://github.com/hackebrot/jinja2-time):
    adds a `now` tag that provides convenient access to the
    [arrow.now()](http://crsmithdev.com/arrow/#arrow.factory.ArrowFactory.now)
    API.
- [`jinja2_jsonschema.JsonSchemaExtension`](https://github.com/copier-org/jinja2-jsonschema):
    adds a `jsonschema` filter for validating data against a JSON/YAML schema.

Search for more extensions on GitHub using the
[jinja2-extension topic](https://github.com/topics/jinja2-extension), or
[other Jinja2 topics](https://github.com/search?q=jinja&type=topics), or
[on PyPI using the jinja + extension keywords](https://pypi.org/search/?q=jinja+extension).

### `message_after_copy`[¶](https://copier.readthedocs.io/en/stable/configuring/#message_after_copy "Permanent link")

- Format: `str`
- CLI flags: N/A
- Default value: `""`

A message to be printed after
[generating](https://copier.readthedocs.io/en/stable/generating/) or
[regenerating](https://copier.readthedocs.io/en/stable/generating/#regenerating-a-project "Regenerating a project")
a project _successfully_.

If the message contains Jinja code, it will be rendered with the same context
as the rest of the template. A
[Jinja include](https://copier.readthedocs.io/en/stable/configuring/#importing-jinja-templates-and-macros "Importing Jinja templates and macros")
expression may be used to import a message from a file.

The message is suppressed when Copier is run in
[quiet mode](https://copier.readthedocs.io/en/stable/configuring/#quiet).

Example

```copier.yml
project_name:
    type: str
    help: An awesome project needs an awesome name. Tell me yours.

_message_after_copy: |
    Your project "{{ project_name }}" has been created successfully!

    Next steps:

    1. Change directory to the project root:

       $ cd {{ _copier_conf.dst_path }}

    2. Read "CONTRIBUING.md" and start coding.

```

### `message_after_update`[¶](https://copier.readthedocs.io/en/stable/configuring/#message_after_update "Permanent link")

- Format: `str`
- CLI flags: N/A
- Default value: `""`

Like
[`message_after_copy`](https://copier.readthedocs.io/en/stable/configuring/#message_after_copy)
but printed after
[_updating_](https://copier.readthedocs.io/en/stable/updating/) a project.

Example

```copier.yml
project_name:
    type: str
    help: An awesome project needs an awesome name. Tell me yours.

_message_after_update: |
    Your project "{{ project_name }}" has been updated successfully!
    In case there are any conflicts, please resolve them. Then,
    you're done.

```

### `message_before_copy`[¶](https://copier.readthedocs.io/en/stable/configuring/#message_before_copy "Permanent link")

- Format: `str`
- CLI flags: N/A
- Default value: `""`

Like
[`message_after_copy`](https://copier.readthedocs.io/en/stable/configuring/#message_after_copy)
but printed _before_
[generating](https://copier.readthedocs.io/en/stable/generating/) or
[regenerating](https://copier.readthedocs.io/en/stable/generating/#regenerating-a-project "Regenerating a project")
a project.

Example

```copier.yml
project_name:
    type: str
    help: An awesome project needs an awesome name. Tell me yours.

_message_before_copy: |
    Thanks for generating a project using our template.

    You'll be asked a series of questions whose answers will be used to
    generate a tailored project for you.

```

### `message_before_update`[¶](https://copier.readthedocs.io/en/stable/configuring/#message_before_update "Permanent link")

- Format: `str`
- CLI flags: N/A
- Default value: `""`

Like
[`message_before_copy`](https://copier.readthedocs.io/en/stable/configuring/#message_after_copy "message_after_copy")
but printed before
[_updating_](https://copier.readthedocs.io/en/stable/updating/) a project.

Example

```copier.yml
project_name:
    type: str
    help: An awesome project needs an awesome name. Tell me yours.

_message_before_update: |
    Thanks for updating your project using our template.

    You'll be asked a series of questions whose answers are pre-populated
    with previously entered values. Feel free to change them as needed.

```

### `migrations`[¶](https://copier.readthedocs.io/en/stable/configuring/#migrations "Permanent link")

- Format: `List[str|List[str]|dict]`
- CLI flags: N/A
- Default value: `[]`

Migrations are like
[tasks](https://copier.readthedocs.io/en/stable/configuring/#tasks), but each
item can have additional keys:

- **command**: The migration command to run
- **version** (optional): Indicates the version that the template update has
    to go through to trigger this migration. It is evaluated using
    [PEP 440](https://www.python.org/dev/peps/pep-0440/). If no version is
    specified the migration will run on every update.
- **when** (optional): Specifies a condition that needs to hold for the task
    to run. By default, a migration will run in the after upgrade stage.
- **working\_directory** (optional): Specifies the directory in which the
    command will be run. Defaults to the destination directory.

If a `str` or `List[str]` is given as a migrator it will be treated as
`command` with all other items not present.

Migrations will run in the same order as declared here (so you could even run a
migration for a higher version before running a migration for a lower version
if the higher one is declared before and the update passes through both).

When `version` is given they will only run when _new version >= declared
version > old version_. Your template will only be marked as
[unsafe](https://copier.readthedocs.io/en/stable/configuring/#unsafe) if this
condition is true. Migrations will also only run when updating (not when
copying for the 1st time).

If the migrations definition contains Jinja code, it will be rendered with the
same context as the rest of the template.

There are a number of additional variables available for templating of
migrations. Those variables are also passed to the migration process as
environment variables. Migration processes will receive these variables:

- `_stage`/`$STAGE`: Either `before` or `after`.
- `_version_from`/`$VERSION_FROM`:
    [Git commit description](https://git-scm.com/docs/git-describe) of the
    template as it was before updating.
- `_version_to`/`$VERSION_TO`:
    [Git commit description](https://git-scm.com/docs/git-describe) of the
    template as it will be after updating.
- `_version_current`/`$VERSION_CURRENT`: The `version` detector as you
    indicated it when describing migration tasks (only when `version` is given).
- `_version_pep440_from`/`$VERSION_PEP440_FROM`, `_version_pep440_to`/
    `$VERSION_PEP440_TO`, `_version_pep440_current`/`$VERSION_PEP440_CURRENT`:
    Same as the above, but normalized into a standard
    [PEP 440](https://www.python.org/dev/peps/pep-0440/) version. In Jinja
    templates these are represented as
    [packaging.version.Version](https://packaging.pypa.io/en/stable/version.html#packaging.version.Version)
    objects and allow access to their attributes. As environment variables
    they are represented as strings. If you use variables to perform
    migrations, you probably will prefer to use these variables.

Example

```copier.yml
_migrations:
  # {{ _copier_conf.src_path }} points to the path where the template was
  # cloned, so it can be helpful to run migration scripts stored there.
  - invoke -r {{ _copier_conf.src_path }} -c migrations migrate $STAGE $VERSION_FROM $VERSION_TO
  - version: v1.0.0
    command: rm ./old-folder
    when: "{{ _stage == 'before' }}"

```

In Copier versions before v9.3.0 a different configuration format had to be
used. This format is still available, but will raise a warning when used.

Each item in the list is a `dict` with the following keys:

- **version**: Indicates the version that the template update has to go
    through to trigger this migration. It is evaluated using
    [PEP 440](https://www.python.org/dev/peps/pep-0440/).
- **before** (optional): Commands to execute before performing the update.
    The answers file is reloaded after running migrations in this stage, to let
    you migrate answer values.
- **after** (optional): Commands to execute after performing the update.

The migration variables mentioned above are available as environment variables,
but can't be used in jinja templates.

### `min_copier_version`[¶](https://copier.readthedocs.io/en/stable/configuring/#min_copier_version "Permanent link")

- Format: `str`
- CLI flags: N/A
- Default value: N/A

Specifies the minimum required version of Copier to generate a project from
this template. The version must be follow the
[PEP 440](https://www.python.org/dev/peps/pep-0440/) syntax. Upon generating or
updating a project, if the installed version of Copier is less than the
required one, the generation will be aborted and an error will be shown to the
user.

Info

If Copier detects that there is a major version difference, it will warn you
about possible incompatibilities. Remember that a new major release means that
some features can be dropped or changed, so it's probably a good idea to ask
the template maintainer to update it.

Example

```copier.yml
_min_copier_version: "4.1.0"

```

### `pretend`[¶](https://copier.readthedocs.io/en/stable/configuring/#pretend "Permanent link")

- Format: `bool`
- CLI flags: `-n`, `--pretend`
- Default value: `False`

Run but do not make any changes.

Info

Not supported in `copier.yml`.

### `preserve_symlinks`[¶](https://copier.readthedocs.io/en/stable/configuring/#preserve_symlinks "Permanent link")

- Format: `bool`
- CLI flags: N/A
- Default value: `False`

Keep symlinks as symlinks. If this is set to `False` symlinks will be replaced
with the file they point to.

When set to `True` and the symlink ends with the template suffix (`.jinja` by
default) the target path of the symlink will be rendered as a jinja template.

### `quiet`[¶](https://copier.readthedocs.io/en/stable/configuring/#quiet "Permanent link")

- Format: `bool`
- CLI flags: `-q`, `--quiet`
- Default value: `False`

Suppress status output.

Info

Not supported in `copier.yml`.

### `secret_questions`[¶](https://copier.readthedocs.io/en/stable/configuring/#secret_questions "Permanent link")

- Format: `List[str]`
- CLI flags: N/A
- Default value: `[]`

Question variables to mark as secret questions. This is especially useful when
questions are provided in the
[simplified prompt
format](https://copier.readthedocs.io/en/stable/configuring/#questions
"Questions").
It's equivalent to configuring `secret: true` in the
[advanced prompt
format](https://copier.readthedocs.io/en/stable/configuring/#advanced-prompt-formatting
"Advanced prompt formatting").

Example

```copier.yml
_secret_questions:
    - password

user: johndoe
password: s3cr3t

```

### `skip_if_exists`[¶](https://copier.readthedocs.io/en/stable/configuring/#skip_if_exists "Permanent link")

- Format: `List[str]`
- CLI flags: `-s`, `--skip`
- Default value: `[]`

[Patterns](https://copier.readthedocs.io/en/stable/configuring/#patterns-syntax "Patterns syntax")
for files/folders that must be skipped only if they already exist, but always
be present. If they do not exist in a project during an `update` operation,
they will be recreated.

Each pattern can be templated using Jinja.

Example

For example, it can be used if your project generates a password the 1st time
and you don't want to override it next times:

```copier.yml
_skip_if_exists:
    - .secret_password.yml

```

.secret\_password.yml.jinja

```jinja
{{999999999999999999999999999999999|ans_random|hash('sha512')}}

```

### `skip_tasks`[¶](https://copier.readthedocs.io/en/stable/configuring/#skip_tasks "Permanent link")

- Format: `bool`
- CLI Flags: `-T`, `--skip-tasks`
- Default value: `False`

Skip template
[tasks](https://copier.readthedocs.io/en/stable/configuring/#tasks) execution,
if set to `True`.

Note

It only skips
[tasks](https://copier.readthedocs.io/en/stable/configuring/#tasks), not
[migration
tasks](https://copier.readthedocs.io/en/stable/configuring/#migrations
"migrations").

Does it imply `--trust`?

This flag does not imply
[`--trust`](https://copier.readthedocs.io/en/stable/configuring/#unsafe "unsafe"),
and will do nothing if not used with.

### `subdirectory`[¶](https://copier.readthedocs.io/en/stable/configuring/#subdirectory "Permanent link")

- Format: `str`
- CLI flags: N/A
- Default value: N/A

Subdirectory to use as the template root when generating a project. If not
specified, the root of the template is used.

This allows you to keep separate the template metadata and the template code.

Tip

If your template is meant to be applied to other templates (a.k.a. recursive
templates), use this option to be able to use
[updates](https://copier.readthedocs.io/en/stable/updating/).

Example

```copier.yml
_subdirectory: template

```

Can I have multiple templates in a single repo using this option?

The Copier recommendation is: **1 template = 1 Git repository**.

Why? Unlike almost all other templating engines, Copier supports
[smart project updates](https://copier.readthedocs.io/en/stable/updating/). For
that, Copier needs to know in which version it was copied last time, and to
which version you are evolving. Copier gets that information from Git tags. Git
tags are shared across the whole Git repository. Using a repository to host
multiple templates would lead to many corner case situations that we don't want
to support.

So, in Copier, the subdirectory option is just there to let template owners
separate templates metadata from template source code. This way, for example,
you can have different dotfiles for you template and for the projects it
generates.

Example project with different `.gitignore` files

Project layout

```text
📁 my_copier_template
├── 📄 copier.yml       # 
├── 📄 .gitignore       # 
└── 📁 template         # 
    └── 📄 .gitignore   # 

```

However, it is true that the value of this option can itself be templated. This
would let you have different templates that all use the same questionnaire, and
the used template would be saved as an answer. It would let the user update
safely and change that option in the future.

Example

With this questions file and this directory structure, the user will be
prompted which Python engine to use, and the project will be generated using
the subdirectory whose name matches the answer from the user:

```copier.yaml
_subdirectory: "{{ python_engine }}"
python_engine:
    type: str
    choices:
        - poetry
        - pipenv

```

Project layout

```text
📁 my_copier_template
├── 📄 copier.yaml # 
├── 📁 poetry
│   ├── 📄 {{ _copier_conf.answers_file }}.jinja # 
│   └── 📄 pyproject.toml.jinja
└── 📁 pipenv
    ├── 📄 {{ _copier_conf.answers_file }}.jinja
    └── 📄 Pipfile.jinja

```

### `tasks`[¶](https://copier.readthedocs.io/en/stable/configuring/#tasks "Permanent link")

- Format: `List[str|List[str]|dict]`
- CLI flags: N/A
- Default value: `[]`

Commands to execute after generating or updating a project from your template.

They run ordered, and with the `$STAGE=task` variable in their environment.
Each task runs in its own subprocess.

If a `dict` is given it can contain the following items:

- **command**: The task command to run.
- **when** (optional): Specifies a condition that needs to hold for the task
    to run.
- **working\_directory** (optional): Specifies the directory in which the
    command will be run. Defaults to the destination directory.

If a `str` or `List[str]` is given as a task it will be treated as `command`
with all other items not present.

Refer to the example provided below for more information.

Example

```copier.yml
_tasks:
    # Strings get executed under system's default shell
    - "git init"
    - "rm {{ name_of_the_project }}/README.md"
    # Arrays are executed without shell, saving you the work of escaping arguments
    - [invoke, "--search-root={{ _copier_conf.src_path }}", after-copy]
    # You are able to output the full conf to JSON, to be parsed by your script
    - [invoke, end-process, "--full-conf={{ _copier_conf|to_json }}"]
    # Your script can be run by the same Python environment used to run Copier
    - ["{{ _copier_python }}", task.py]
    # Run a command during the initial copy operation only, excluding updates
    - command: ["{{ _copier_python }}", task.py]
      when: "{{ _copier_operation == 'copy' }}"
    # OS-specific task (supported values are "linux", "macos", "windows" and `None`)
    - command: rm {{ name_of_the_project }}/README.md
      when: "{{ _copier_conf.os in  ['linux', 'macos'] }}"
    - command: Remove-Item {{ name_of_the_project }}\\README.md
      when: "{{ _copier_conf.os == 'windows' }}"

```

Note: the example assumes you use [Invoke](https://www.pyinvoke.org/) as your
task manager. But it's just an example. The point is that we're showing how to
build and call commands.

### `templates_suffix`[¶](https://copier.readthedocs.io/en/stable/configuring/#templates_suffix "Permanent link")

- Format: `str`
- CLI flags: N/A
- Default value: `.jinja`

Suffix that instructs which files are to be processed by Jinja as templates.

Example

```copier.yml
_templates_suffix: .my-custom-suffix

```

An empty suffix is also valid, and will instruct Copier to copy and render
_every file_, except those that are
[excluded by default](https://copier.readthedocs.io/en/stable/configuring/#exclude).
If an error happens while trying to read a file as a template, it will
fallback to a simple copy (it will typically happen for binary files like
images). At the contrary, if such an error happens and the templates suffix is
_not_ empty, Copier will abort and print an error message.

Example

```copier.yml
_templates_suffix: ""

```

If there is a file with the template suffix next to another one without it, the
one without suffix will be ignored.

```example
📁 my_copier_template
├── 📄 README.md           # Your template's README, ignored at rendering
├── 📄 README.md.jinja     # README that will be rendered
└── 📄 CONTRIBUTING.md     # Used both for the template and the subprojects

```

Warning

Copier 5 and older had a different default value: `.tmpl`. If you wish to keep
it, add it to your `copier.yml` to keep it future-proof.

Copier 6 will apply that old default if your
[min\_copier\_version](https://copier.readthedocs.io/en/stable/configuring/#min_copier_version)
is lower than 6.

Copier 7+ no longer uses the old default independent of
[min\_copier\_version](https://copier.readthedocs.io/en/stable/configuring/#min_copier_version).

### `unsafe`[¶](https://copier.readthedocs.io/en/stable/configuring/#unsafe "Permanent link")

- Format: `bool`
- CLI flags: `--UNSAFE`, `--trust`
- Default value: `False`

Copier templates can use dangerous features that allow arbitrary code execution:

- [Jinja extensions](https://copier.readthedocs.io/en/stable/configuring/#jinja_extensions "jinja_extensions")
- [Migrations](https://copier.readthedocs.io/en/stable/configuring/#migrations "migrations")
- [Tasks](https://copier.readthedocs.io/en/stable/configuring/#tasks "tasks")

Therefore, these features are disabled by default and Copier will raise an
error (and exit from the CLI with code `4`) when they are found in a template.
In this case, please verify that no malicious code gets executed by any of the
used features. When you're sufficiently confident or willing to take the risk,
set `unsafe=True` or pass the CLI switch `--UNSAFE` or `--trust`.

Danger

Please be sure you understand the risks when allowing unsafe features!

Info

Not supported in `copier.yml`.

Tip

See the
[`trust` setting](https://copier.readthedocs.io/en/stable/settings/#trusted-locations "Trusted locations")
to mark some repositories as always trusted.

### `use_prereleases`[¶](https://copier.readthedocs.io/en/stable/configuring/#use_prereleases "Permanent link")

- Format: `bool`
- CLI flags: `g`, `--prereleases`
- Default value: `False`

Imagine that the template supports updates and contains these 2 Git tags:
`v1.0.0` and `v2.0.0a1`. Copier will copy by default `v1.0.0` unless you add
`--prereleases`.

Also, if you run
[`copier
update`](https://copier.readthedocs.io/en/stable/reference/cli/#copier._cli.CopierUpdateSubApp
"CopierUpdateSubApp"),
Copier would ignore the `v2.0.0a1` tag unless this flag is enabled.

Warning

This behaviour is new from Copier 5.0.0. Before that release, prereleases were
never ignored.

Info

Not supported in `copier.yml`.

### `vcs_ref`[¶](https://copier.readthedocs.io/en/stable/configuring/#vcs_ref "Permanent link")

- Format: `str`
- CLI flags: `-r`, `--vcs-ref`
- Default value: N/A (use latest release)

When copying or updating from a Git-versioned template, indicate which template
version to copy.

This is stored automatically in the answers file, like this:

Info

Not supported in `copier.yml`.

By default, Copier will copy from the last release found in template Git tags,
sorted as [PEP 440](https://www.python.org/dev/peps/pep-0440/).

## Patterns syntax[¶](https://copier.readthedocs.io/en/stable/configuring/#patterns-syntax "Permanent link")

Copier supports matching names against patterns in a gitignore style fashion.
This works for the options `exclude` and `skip`. This means you can write
patterns as you would for any `.gitignore` file. The full range of the
gitignore syntax is supported via
[pathspec](https://github.com/cpburnz/python-path-specification).

For example, with the following settings in your `copier.yml` file would
exclude all files ending with `txt` from being copied to the destination
folder, except the file `a.txt`.

```yaml
_exclude:
    # match all text files...
    - "*.txt"
    # .. but not this one:
    - "!a.txt"

```

## The `.copier-answers.yml` file[¶](https://copier.readthedocs.io/en/stable/configuring/#the-copier-answersyml-file "Permanent link")

If the destination path exists and a `.copier-answers.yml` file is present
there, it will be used to load the last user's answers to the questions made in
[the `copier.yml`
file](https://copier.readthedocs.io/en/stable/configuring/#the-copieryml-file
"The copier.yml file").

This makes projects easier to update because when the user is asked, the
default answers will be the last ones they used.

The file **must be called exactly `{{ _copier_conf.answers_file }}.jinja`** (or
ended with
[your chosen
suffix](https://copier.readthedocs.io/en/stable/configuring/#templates_suffix
"templates_suffix"))
in your template's root folder) to allow
[applying multiple templates to the same
subproject](https://copier.readthedocs.io/en/stable/configuring/#applying-multiple-templates-to-the-same-subproject
"Applying multiple templates to the same subproject").

The default name will be `.copier-answers.yml`, but
[you can define a different default path for this
file](https://copier.readthedocs.io/en/stable/configuring/#answers_file
"answers_file").

The file must have this content:

```yaml
# Changes here will be overwritten by Copier; NEVER EDIT MANUALLY
{{ _copier_answers|to_nice_yaml -}}

```

The builtin `_copier_answers` variable includes all data needed to smooth
future updates of this project. This includes (but is not limited to) all
JSON-serializable values declared as user questions in
[the `copier.yml`
file](https://copier.readthedocs.io/en/stable/configuring/#the-copieryml-file
"The copier.yml file").

As you can see, you also have the power to customize what will be logged here.
Keys that start with an underscore (`_`) are specific to Copier. Other keys
should match questions in `copier.yml`.

The path to the answers file must be expressed relative to the project root,
because:

- Its value must be available at render time.
- It is used to update projects, and for that a project must be git-tracked.
    So, the file must be in the repo anyway.

### Applying multiple templates to the same subproject[¶](https://copier.readthedocs.io/en/stable/configuring/#applying-multiple-templates-to-the-same-subproject "Permanent link")

Imagine this scenario:

1. You use one framework that has a public template to generate a project.
    It's available at
    `https://github.com/example-framework/framework-template.git`.
2. You have a generic template that you apply to all your projects to use the
    same pre-commit configuration (formatters, linters, static type
    checkers…). You have published that in
    `https://gitlab.com/my-stuff/pre-commit-template.git`.
3. You have a private template that configures your subproject to run in your
    internal CI. It's found in
    `git@gitlab.example.com:my-company/ci-template.git`.

All 3 templates are completely independent:

- Anybody can generate a project for the specific framework, no matter if
    they want to use pre-commit or not.
- You want to share the same pre-commit configurations, no matter if the
    subproject is for one or another framework.
- You want to have a centralized CI configuration for all your company
    projects, no matter their pre-commit configuration or the framework they
    rely on.

Well, don't worry. Copier has you covered. You just need to use a different
answers file for each one. All of them contain a
`{{ _copier_conf.answers_file }}.jinja` file
[as specified
above](https://copier.readthedocs.io/en/stable/configuring/#the-copier-answersyml-file
"The .copier-answers.yml file").
Then you apply all the templates to the same project:

```bash
mkdir my-project
cd my-project
git init
# Apply framework template
copier copy -a .copier-answers.main.yml https://github.com/example-framework/framework-template.git .
git add .
git commit -m 'Start project based on framework template'
# Apply pre-commit template
copier copy -a .copier-answers.pre-commit.yml https://gitlab.com/my-stuff/pre-commit-template.git .
git add .
pre-commit run -a  # Just in case 😉
git commit -am 'Apply pre-commit template'
# Apply internal CI template
copier copy -a .copier-answers.ci.yml git@gitlab.example.com:my-company/ci-template.git .
git add .
git commit -m 'Apply internal CI template'

```

Done!

After a while, when templates get new releases, updates are handled separately
for each template:

```bash
copier update -a .copier-answers.main.yml
copier update -a .copier-answers.pre-commit.yml
copier update -a .copier-answers.ci.yml

```
