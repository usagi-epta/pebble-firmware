#!/usr/bin/env python
# Copyright 2024 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


from __future__ import with_statement
from string import Template
import re, fnmatch, os

VERSION = "0.10.0"

TEST_FUNC_REGEX = r"^(void\s+(%s__(\w+))\(\s*void\s*\))\s*\{"

EVENT_CB_REGEX = re.compile(
    r"^(void\s+clar_on_(\w+)\(\s*void\s*\))\s*\{",
    re.MULTILINE)

SKIP_COMMENTS_REGEX = re.compile(
    r'//.*?$|/\*.*?\*/|\'(?:\\.|[^\\\'])*\'|"(?:\\.|[^\\"])*"',
    re.DOTALL | re.MULTILINE)

CATEGORY_REGEX = re.compile(r"CL_IN_CATEGORY\(\s*\"([^\"]+)\"\s*\)")

CLAR_HEADER = """
/*
 * Clar v%s
 *
 * This is an autogenerated file. Do not modify.
 * To add new unit tests or suites, regenerate the whole
 * file with `./clar`
 */
""" % VERSION

CLAR_EVENTS = [
    'init',
    'shutdown',
    'test',
    'suite'
]

def main():
    from optparse import OptionParser

    parser = OptionParser()

    parser.add_option('-c', '--clar-path', dest='clar_path')
    parser.add_option('-v', '--report-to', dest='print_mode', default='default')
    parser.add_option('-f', '--file', dest='file')

    options, args = parser.parse_args()

    folder = args[0] or '.'
    print('folder: %s' % folder)
    builder = ClarTestBuilder(folder,
        clar_path = options.clar_path,
        print_mode = options.print_mode)

    if options.file is not None:
      builder.load_file(options.file)
    else:
      builder.load_dir(folder)

    builder.render()

class ClarTestBuilder:
    def __init__(self, path, clar_path = None, print_mode = 'default'):
        self.declarations = []
        self.suite_names = []
        self.callback_data = {}
        self.suite_data = {}
        self.category_data = {}
        self.event_callbacks = []

        self.clar_path = os.path.abspath(clar_path) if clar_path else None

        self.path = os.path.abspath(path)
        self.modules = [
            "clar_sandbox.c",
            "clar_fixtures.c",
            "clar_fs.c",
            "clar_mock.c",
            "clar_categorize.c",
        ]

        self.modules.append("clar_print_%s.c" % print_mode)

    def load_dir(self, folder):
        print("Loading test suites...")

        for root, dirs, files in os.walk(self.path):
            module_root = root[len(self.path):]
            module_root = [c for c in module_root.split(os.sep) if c]

            tests_in_module = fnmatch.filter(files, "*.c")

            for test_file in tests_in_module:
                full_path = os.path.join(root, test_file)
                test_name = "_".join(module_root + [test_file[:-2]])

                with open(full_path) as f:
                    self._process_test_file(test_name, f.read())

    def load_file(self, filename):
        with open(filename, encoding="latin-1") as f:
          test_name = os.path.basename(filename)[:-2]
          self._process_test_file(test_name, f.read())

    def render(self):
        if not self.suite_data:
            raise RuntimeError('No tests found under "%s"' % self.path)

        if not os.path.isdir(self.path):
            os.makedirs(self.path)

        main_file = os.path.join(self.path, 'clar_main.c')
        with open(main_file, "w") as out:
            out.write(self._render_main())

        header_file = os.path.join(self.path, 'clar.h')
        with open(header_file, "w") as out:
            out.write(self._render_header())

        print ('Written Clar suite to "%s"' % self.path)

    #####################################################
    # Internal methods
    #####################################################

    def _render_cb(self, cb):
        return '{"%s", &%s}' % (cb['short_name'], cb['symbol'])

    def _render_suite(self, suite, index):
        template = Template(
r"""
    {
        ${suite_index},
        "${clean_name}",
        ${initialize},
        ${cleanup},
        ${categories},
        ${cb_ptr}, ${cb_count}
    }
""")

        callbacks = {}
        for cb in ['initialize', 'cleanup']:
            callbacks[cb] = (self._render_cb(suite[cb])
                if suite[cb] else "{NULL, NULL}")

        if len(self.category_data[suite['name']]) > 0:
            cats = "_clar_cat_%s" % suite['name']
        else:
            cats = "NULL"

        return template.substitute(
            suite_index = index,
            clean_name = suite['name'].replace("_", "::"),
            initialize = callbacks['initialize'],
            cleanup = callbacks['cleanup'],
            categories = cats,
            cb_ptr = "_clar_cb_%s" % suite['name'],
            cb_count = suite['cb_count']
        ).strip()

    def _render_callbacks(self, suite_name, callbacks):
        template = Template(
r"""
static const struct clar_func _clar_cb_${suite_name}[] = {
    ${callbacks}
};
""")
        callbacks = [
            self._render_cb(cb)
            for cb in callbacks
            if cb['short_name'] not in ('initialize', 'cleanup')
        ]

        return template.substitute(
            suite_name = suite_name,
            callbacks = ",\n\t".join(callbacks)
        ).strip()

    def _render_categories(self, suite_name, categories):
        template = Template(
r"""
static const char *_clar_cat_${suite_name}[] = { "${categories}", NULL };
""")
        if len(categories) > 0:
            return template.substitute(
                suite_name = suite_name,
                categories = '","'.join(categories)
                ).strip()
        else:
            return ""

    def _render_event_overrides(self):
        overrides = []
        for event in CLAR_EVENTS:
            if event in self.event_callbacks:
                continue

            overrides.append(
                "#define clar_on_%s() /* nop */" % event
            )

        return '\n'.join(overrides)

    def _render_header(self):
        template = Template(self._load_file('clar.h'))

        declarations = "\n".join(
            "extern %s;" % decl
            for decl in sorted(self.declarations)
        )

        return template.substitute(
            extern_declarations = declarations,
        )

    def _render_main(self):
        template = Template(self._load_file('clar.c'))
        suite_names = sorted(self.suite_names)

        suite_data = [
            self._render_suite(self.suite_data[s], i)
            for i, s in enumerate(suite_names)
        ]

        callbacks = [
            self._render_callbacks(s, self.callback_data[s])
            for s in suite_names
        ]

        callback_count = sum(
            len(cbs) for cbs in self.callback_data.values()
        )

        categories = [
            self._render_categories(s, self.category_data[s])
            for s in suite_names
        ]

        return template.substitute(
            clar_modules = self._get_modules(),
            clar_callbacks = "\n".join(callbacks),
            clar_categories = "".join(categories),
            clar_suites = ",\n\t".join(suite_data),
            clar_suite_count = len(suite_data),
            clar_callback_count = callback_count,
            clar_event_overrides = self._render_event_overrides(),
        )

    def _load_file(self, filename):
        if self.clar_path:
            filename = os.path.join(self.clar_path, filename)
            with open(filename) as cfile:
                return cfile.read()

        else:
            import zlib, base64, sys
            content = CLAR_FILES[filename]

            if sys.version_info >= (3, 0):
                content = bytearray(content, 'utf_8')
                content = base64.b64decode(content)
                content = zlib.decompress(content)
                return str(content, 'utf-8')
            else:
                content = base64.b64decode(content)
                return zlib.decompress(content)

    def _get_modules(self):
        return "\n".join(self._load_file(f) for f in self.modules)

    def _skip_comments(self, text):
        def _replacer(match):
            s = match.group(0)
            return "" if s.startswith('/') else s

        return re.sub(SKIP_COMMENTS_REGEX, _replacer, text)

    def _process_test_file(self, suite_name, contents):
        contents = self._skip_comments(contents)

        self._process_events(contents)
        self._process_declarations(suite_name, contents)
        self._process_categories(suite_name, contents)

    def _process_events(self, contents):
        for (decl, event) in EVENT_CB_REGEX.findall(contents):
            if event not in CLAR_EVENTS:
                continue

            self.declarations.append(decl)
            self.event_callbacks.append(event)

    def _process_declarations(self, suite_name, contents):
        callbacks = []
        initialize = cleanup = None

        regex_string = TEST_FUNC_REGEX % suite_name
        regex = re.compile(regex_string, re.MULTILINE)

        for (declaration, symbol, short_name) in regex.findall(contents):
            data = {
                "short_name" : short_name,
                "declaration" : declaration,
                "symbol" : symbol
            }

            if short_name == 'initialize':
                initialize = data
            elif short_name == 'cleanup':
                cleanup = data
            else:
                callbacks.append(data)

        if not callbacks:
            return

        tests_in_suite = len(callbacks)

        suite = {
            "name" : suite_name,
            "initialize" : initialize,
            "cleanup" : cleanup,
            "cb_count" : tests_in_suite
        }

        if initialize:
            self.declarations.append(initialize['declaration'])

        if cleanup:
            self.declarations.append(cleanup['declaration'])

        self.declarations += [
            callback['declaration']
            for callback in callbacks
        ]

        callbacks.sort(key=lambda x: x['short_name'])
        self.callback_data[suite_name] = callbacks
        self.suite_data[suite_name] = suite
        self.suite_names.append(suite_name)

        print("  %s (%d tests)" % (suite_name, tests_in_suite))

    def _process_categories(self, suite_name, contents):
        self.category_data[suite_name] = [
            cat for cat in CATEGORY_REGEX.findall(contents) ]


CLAR_FILES = {
"clar.c" : r"""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""",
"clar_print_default.c" : r"""eJyFU8Fu2zAMPdtfwQUwIgVuenew9tZTsMuwU1sYqiW3AhzJkOhswNB/n0Q5rRws6Ukmxff4RD6XHgXqDo5WS+gG4drRaYOtNhpZ+ABUHtvOTgZriLGfNKpTorPGI3RvwsEmXRhxUJ6Xf8uCRUr+Cd+VBVH3bLW3QioJlUxsvoHKP5lVDbEjX3TIWTOGnygcKhlAIftelhde4d8mlPa3+folMaGcsy4lLr0gpTLkRy4D78pPoU8maSxIlVOjddhSrWdXpVMN6TbT4TRpj27qMJVRAWzoILmnlhAGy+FB6GFyqqG5Bgqeq6p801QeWOU5PIagks/weIPhiOVlURDrzR09NIvjLGK4Mhak8p3TI2q7gPR6yBGDNmF90+FFuTOeObvQBScjzHVpqAf/SlW6BzZfZM3h23f48Wu/54H+Ek9Wzpfbue4fa6JSlts8SQ9+TJ7JXpISfZi7kuf+iYDdMkOYzNJVF/QmNNzD+mENDay36y/00YbY///D3ObaSPWHVN1uwFg7wuZ2aWeqOLN4kn2tv3gJhl70D9uqYbvdUrOjaAcdroR7HXcU+vjnshjXkBZbHPt5Bh5lWBjla4LwhFFGsjl8L/8BsUiTTQ==""",
"clar_print_tap.c" : r"""eJyNVE1vnDAQPcOvmGWFBAiQot6yaqr2HFU9tLdKyAGzscLayDbbVlX+e8cDJPbuJtsTzPObmTcfdmwss6KFoxIdtAPTzaiFtI2Qwmb4A5Yb27RqkrYEZ5tJWL4CrZLGQvvINBTzgWQHbvL4bxxlLmT+6r5bIY94gq08ktBnyffP3+DItRFKws2HnzLJd/FzHL8h2TxOtlO/5HXZDuBaKz0D/yM3xDznXRxHoodsEwSMXmrYwsiM4R2wYYC0I2GZybGY0hOJhUV8MDxw7JkY0BGd2EHJ/am3l7BEvyiMtoa5qeu0O8/2dhspLPVQTod1xMbqqbUzjQhQ0MdrHbJdL9a8AFVVzSPzMJy5YXsOt5Ca1yKqu7mWg9mHdMNx/ML+uaVenEWj0QCcRSM8pLri4QLV4SGzx6ZfYjo8ZA5CrszOZzq8wXY8cJ2v67Ecddy0WozWbfTmI3z9cX/vLwuARzgV4B3lYafrur52OZSk1fEvLO2Du4bzhZhNUj0D8/rRhNdUqXFLWC3CUPiyop8gkcqCekqwGQl+3Jkf8MXEdHFE8kmc5qPSy86Z7EoFNNbs8pvj33IhO/470L2FoihQNWTbtMudQY313X3X92WwB5QcyMC9Ld0QKOeRNYPAI6b3445MjIQOzi5hWfF+UWbwxZrwRUq+YCMBfzdAO348JVAKFyKfY3LZZYv5HP8D5Mbj9w==""",
"clar_sandbox.c" : r"""eJydVf1L40AQ/Tn5K8YWbGKrjR/ccVQPDvSknF/YioKWJSYbu5hsSnbbuyr+7ze7m7RJWvU4EZpmZmfeezNv22Q8iKchhUMhw5g97oy/27aQvmQBBGM/AxLEfkYmvhzfH3jfvox6izDj0maCzPyYhUQmE53kBCkX0hzdUi9c+9W2BsMfQzIEIfG0xSJwVAlHhTuwKaQLG0fgubZlZVROMw5ekbcxIP3Bcf8aD+wISZI0pG49L392/CCgQuRVb8nlLxeOVNme/VbBHDFexquRPk6jiGYdEOyFEgkx5U8GepNFPKQRkNv+xf6ebRXSaJZ59gwFCtIpl3AEB71ajqlP+QyFysT9CHNQEKsxPL9CXo0OqCf9cWI+bwYn11fXlz/7ZycNG6w3pAhW3okpvlGagcOwjtcDBofL9j1ot5mry9d6Y/ITlfjgLICwEQpjGZHxpRJVnZKMT6nqoiOr41WppgXSzHgwmTuFdhjqFMqp0qUhWdabjf+21d2CfgRyTFU2y1KeUJQtTKngLdTTn4PP53LM+FMHZDYHmcJUUOhif9jq2u+Aaqh4I8dVh2WCFWQlYAiqSWNBTelTKoc0mVypos7x7eX1sWuOdcCUqy1fk/KQRYbXcMwEiLmQNFkQitkzRQIVLop8MM0yTZxlNJApBj8gt/Mus52PaBVft3fLBpilLARt6SkXPg8f0z+OeqdtqgCU/O6NlIFaD15ryRpXAy1RdkQwRhaIEmGWBIkEyZJSMeNCs5DJc4giTXLrqcfYl9St3CyoN4tDkkM0SixwlrZbBYj0Wayd1dD9lHR3+q+h3LiwdHGpVC+AJUZj/zQqw3bRYOWbSalpW1gMu+E88KFKsq7OK+Bq8DRLcKgvVMNVi3B1OejfATr5t5+FIGJfjKnQS1CyurVidUViafL6vFg+rwc9L8uqhaDVbS2suBhUrYZitg27I3UjY75pVI2328tias+KtVxmQVsh7SyHs05ZbINJuWSAmjFOQ4eQ8/7F6e3+HiFuDi551ttSPoo0L27OzlbmovJxu3Afy1P1vnreyk+MOoDOL7fWI6t2JeLT/VhT93+AFFdQYY7P6S5GuPR95YfO2PzfTQ6bm+tct94BqopxfhnoWi0q8P4CB3+S+g==""",
"clar_fixtures.c" : r"""eJyFUV1LwzAUfW5+xZU9rLUVJ4ggZQ9DFAUfZEwQSglZmrBAl5Qkk6n43236tWbKfMvNOfecc+81llhBgSppLNAN0XCOuNjbnWa4InYTjpE1MSzxuD1Vki2L0BcKTKfn0EYgu57d3uRpjYhPhi1opSwumUwRCvo3zMFYXT9C5xA5stWSVh9hI5FAa+wUFG//osgJCA5tmQ1SF3CVw9kcppfTCAWBj8ZxDg3UN4/zZ7MaHBrHSBw7vpcJ4mGS5Ijtai9qnannNqk1q7myXU+KvhGaCF4wDnfPiyV+eHpbvS7v8cti9YjGq6Yl7lzCkxfo1L0j/lJOwOtrUrwrUcDBBRsii7Xan3bjBlNVL2WUzuMkgGlJdLuIP21oyYjcVf/a6G3ozXTQPRqmsZkwWQiOfgAVGffP""",
"clar_mock.c" : r"""eJy1Vt9r40YQfo7+irGPpvYh55xec9dy2NCXwEGaPpTSh7aYtTSKF0srsVpZyR353zszK1myLR+G0oCJPL9nvm9Gdi8FxphA6WwVOfg1j7YPunSPeYzwNYBB+VuDz+7TOWVhccfKKDelg2ijLLxNKhOxrNLGZep55WCn0golRqm/IAmivDIU9PUg2qcgKJ1yOjrMUa4y+rpK6ftqgyqGhdR6fSwPB0Rk9/jHw0MI8xBmt2HwSjm6sqJU2ZW4TPr1+2fuIoQBuU6xlTfdpNrgNOCijiYnTQG8ewd/qnQLboPAtcFaRdta2bgMIckt3H++/w3WuFE7ndsbcmDhhL2p1+OebmTkINrR4rTnRrWQf7MlW09lYAA68VFnS24OFgsZTqsVEJ02HimAV8C0RHEi6KOs6PmGMp4ph5h3/muLats4B/y5itKVKku0bjU5W3AI48ccstwisMKTpQS1UzpV6xRH4ymhdkVD/F3tUIYoJjenFNt3vSfcUQGzpTCP6yBGjBkuPy4v1iVoQ7465pwC3OdEMoqRLs33Dgq0mTJoXAhpXqMF7UrvjwJe52SxrFKJ+gVtHkJNcRBjcDmpslyaIWXXNbt3IPmaljCH62uYzfrC/tw7nGdL3tX9ENrFhd53b3jADm+SWETJK40zfBZdZU27u69BsMt13OxMrdN05Q3+++qEDX1O/rzlEcb7AP1Tcm77qNFIpWkeTW5DSZknk77VdHpEElmM0aK5GmPS9FqFWrtNyxDp0uncgFEZer70lwvaM9hjJEn3zDyAsz2Inj6/xMKRNT5pY7R5gjyRuxH0kRw6DS3iHbgwdCH4EA+5NrRomH+vn6vCk591RHj70vLbiDxSJVNYue6y1aoEzAr3QtUnvNLCcMYg9I88TsjUFn2kwesGRU6Y8wh89lrKov3Z6GjD61RzTtqmWhl3M7TlUnEHo+y51Bfl1laFw3jUR+xkM4Tvzcuoo72USkuNbsJCJt3VuUEOTP3U9jxCp7YNq7ijIXXLr/mQsmXZ7PYbjUUpKlMV+9aG9insfg588x0lRpe8o8huf8eGb9fpYTrGYipN8Ut2Q4zBks4x84afyJuWs87tdhS8ocs6D5hYT/T67bXZLDeRSII6+pE0ITMflu0zpQ1LQNmno8NGkt1f//g4h8diwllCuPv4XgovLAVIJmPJTS9O+C7+24xDXwudIV4Gsj0X5vaH9+2pOlX+ePfhvPLjTz9fXABludCSUl5oSflPSlsJIdsCP9yFcPmQyPx/sbzAtOPKnLnxBk2sk+BfzsyiHg==""",
"clar_fs.c" : r"""eJydVdtu20YQfSa/YkAD8TKWL3HSl8otYDhiKlQWA4mG29oCw5BLa1GSS+yufGnrf+/shZTkqDCaF0lzdvbM7JyZ0R4rC1pCej2evj/1/T00WEMhiqM0mpx/mgPRP+fjyWiawD8Gn8YX8TQazy7Pk3E87cHRbBbPrsYvnS5//Tiehb4vVaZYDvkyE/DWL1lFeSvTNlNLkvNGKndikND/2/esrU34CaZXk8nQ9yT7i6YKKtrcqeUA2ND3PVYCSa2b9Qt9zxNUrUTjrvmevYA8Ugn8bf1DJHT0dVZVPCfO7QBOw475FeKa1nn7ZLwGkNovy9Kx31hzgVFOtiGM887BvldyAYQZCxicOZIhHBywELAafTI3bKHz2T/e1+l4PQT7t7f7GOAZyVyS+mzoP/e1v+es6CpPWKOg5gUdwFb5JV+J/CVYUKmMJvNfIuyE+PM8mV1dJFAikU7eutmrmMmWuI5Rl8O6abJvnEwETfUHFfyS1lw8kTeafgBac16S7dBhaIvWyqOHaNXkWkN8zNBhbSR4reU2sXs04YjpUB1SRlV2JxHs+908p0ozKalQKcESY2BMNW6pwCLyxqYVag1OBngcXLOm4A8SXvhBmaFZBL5nUxWUknUpjOke/VIgmYqa7BDFKNDJF8Xpx9FklIyw7TrNTI/u4ss59uj/kHkjyEX8+feNEOk6Z0OOpdL8Fc2aVUs0ZAnMG0r2iH1IncR5lQk3IcHbILQke7SStEsXW9KXS1pVKV8pYpNyGWbi7v5mYbh14+oLK6nHiRW4D/BT1xi/dGNx8SdZzy9iZ3BiZ6hsBd4uiVQFFUKr5wXzJ6loDWhz8SN8sbe/QI4bwUl4dNsEWjOPPjJFDt+Fbso6et0Jlp8+0vyemFxPFgOTdOf8kDGFzvrCAN7Y/Ad4b9hP6/Xot3EyT86Tqzmx565ErMmrVUHhDJcXa+6Olj9/p8C9vtY0ef6wGG7P73rLWjvFTaSL2U83ZlGg1htzvXZcb9j+1NbJmjcbnodm+fWL7L8c7HZ0JUUzOP7KmuO8DYYONU7B4awHThebg2+g9xpyDRW6+TcHHxb9f4sZ+3olFfaolGby171olDTTHpmWAMVB1xyUXmauz6VGZdYUX/nj7rF/ddI3Bn1Dow+LXTUQ9Tc1KLeL0L14RzG+98120EEt6fZLX9kHZvZXjbtCzJ+BhjaAZ9wFTcFK/186nagN""",
"clar_categorize.c" : r"""eJydVd9P2zAQfk7+iqMTVX6B4LkLUsXYXqpNQvAwMRS5qbtZCklnO9MY2v++8zkJbkhS2Eub2L7z93333eXdhm9FyeFytbzOLpc3V5++XH/NPlx9XN6ubmCGu6wu9Mz39eOO4xsoLetcw5Pv5VWpNOQ/mIQoKtkDVwvfEyUuVXWpm2dWFFW+8P9CXjCZ5Uzz75V8zAqh8ISvNNMiH9iDzF0Tf3jGS7Yu+OY5iG7aCxQlxQYD6SLzm4ALGQ+E/pNFKRDttpIQCEjhbAEC3oOJOLmwXCCOReh7nthCgALkTPH8YRdgiqQ5R/zvxH0IKWYwZz3JdS1LOMfczeMZCtHh/1WJTY8A22wyXf0XCQQ2LEYTg+cMKAsERaQIhyJcpA0TqlhoCuw5CxCncI7420Xii2JJTtuBs5q4iSACheWrtoELOwwxE0rhJrtz0MTxPeZG0AcEs6YIeorQHskyLu98zGCklc3wqsszpBkYipkGVQvNM2LQlqlpF4qkbYjoTxG+Js7Yb6+biHkffkN2sFNDc7zvYAcOLsSxMQCdwZR4yuJAz562KmAHG/Ywn5OO9GLDhqGQ/VyVXvYktQlRIwUj1gpjX9ckQ9MeJ+D0FkvWhwqwk3hfW7c9E+wkTrXfbnv73k9VSR2Mlf20se7ovq0qSjFk5+Ql68GKTGfvxgwR2wazY3WsvpWzBCyfCXTd+JmuhlDWhD3Rxkxqe8g1pspZNz2OptkYIm80MGWlm3EOdJ58nlsj8974c6KfDzSModR2g3vtAogtHKXw+Xa1WoB5s90wPm0nYFC2sPdl2P80/AP2l4xl""",
"clar.h" : r"""eJy9V21v2zYQ/lz9CsbeAMrQ2jifhqQpEARJG8DNitTFNiAAIUtUzJZ6KUk1zoL89x1JWRJlKmlaoP4gk8d77oW8O/KmLCtSmiFCThcnV2R59nFJ3hESTIHICrpDD6asSHidUvRaUvU5r16u3/RpKl2VJd8hcrbaobFCubS6YEDWtIBuFBUF0rJQwmNB6KaiiWLFDaliKalQR7s8zQopk6QWgqYtC5hJVnXmcjXEoyD4VrLUrhG7hoMXYBxKyiJlipVFFLyAsQTKOhZoljFOI8vCYY8Gq1SIUgxoKZWJYFUjSwPluqx5SuJVKVTos4HQr3XMicR9OdH4BITuEEDwmFyGNcAHeo6UHNfA8CdRwIl6Qy0GOXJGSNp1jcvjDSCthrxMvjhe23FWF4kroaHr02jokv1HiT0V1+pbxjkRVNWi+HnRUYD8P8vZ+fMt5nUnoJGQlHXRP3ICeUQSTuOirrCh4VkzDe18FkbIDsoq/lr3XCOZdKBa7JRlOqFN2p5f/LP8dHVGPpws3wWOfwBlG9gOit3INjRSxLmjpSHLuID03jwHsrXuEciUQpplQVtyThfk4pKcnizP3v519S+GQRgEr2azAM3QiYk+SCOUx4koJbplao2gOHCWMIVM7qGcShnfUOB/1QoFk/JaKpP9BANAREhnZYjSEt2jazhSXhY39qMTVFBZc4WOkWEOjwwLyxBuFl6j/bABIlQJgGR48raEoIkZBMnNVsDvnKfXxSRq5o0g5NabLOYSAoXAgS3OCNGjxcWlGU3OITiNx0nMuZFO00M0QdPOiQjNG7kP8H1At2tgQng/3HFfw133HTusr9q3EWPOTBmmqUmZzipVGsM8ZvUtaErHk+r3jh/TD/sotWImUQHbrURNfXq3EXO6psmXH4iWROM84eIz+M24wd91eu5BWc2/+KR8JvyCg9p/KrWL8juTujHJl+eXnxYLfyoMQP093wE1rrcIN5ot+3jQPeVHF26dht0Q3DGqi5Uh7FFfDMsQ4fXkvBSJDiKQBiX71W0sCihuQ+uNAZ44GYuOJZWqSYaXE3+xaDQ9R+rfFoLSWug/pZXQDU1qHVWHE0/MLe8qcC4eRN7Qu8GDTM4jeeCa1K7BYhhhWI5aC1sDJx+VsStnMo9VsjbJIOfwhTzSw4ORgtm+2OYR8ytmGBZBMfMqnrJOCXtcyQqv5tFqTMneHiyHkf7zK1p1ilaPK6pwNY+qg14mYaCE6BguXCCPA3MLjLjXxhxvX6SzUMuL+lOwGXPvybyneSnu3JOpOl+qA+dK+UBXK7hfreImZg5HgqZyysZ1cD/SzsBDQxfI5pkB74/Pda5j8xjZNgv7epfeq2TLftx/lvSfLg/m6+SRt2l66jrZ8tvsxWGvpOvKodPrqFM1lA7+mLdOj8W3FS3PQ7vp76ErMNnj327TNGxDwkwI0TefdWPoUDiEEgWVAOtPiLD9b4XuMldKeAAm1MxSH+vUtK4LIaYNwLbzaPsE3Rl4OpapZfMdjAMd0xXz2/hO9pX9mJY/5mMqfl52L7/M7ZBTtS5TKNlaWKyrs63Lv93bpp70VyBMmi7if96WjuM="""
}
if __name__ == '__main__':
    main()
