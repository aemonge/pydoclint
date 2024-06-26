"""Helper functions to classes/methods in visitor.py"""
import ast
import sys
from typing import List, Optional, Set, Union

from pydoclint.utils.annotation import unparseAnnotation
from pydoclint.utils.arg import Arg, ArgList
from pydoclint.utils.doc import Doc
from pydoclint.utils.generic import (
    appendArgsToCheckToV105,
    getDocstring,
    specialEqual,
    stripQuotes,
)
from pydoclint.utils.internal_error import InternalError
from pydoclint.utils.return_anno import ReturnAnnotation
from pydoclint.utils.return_arg import ReturnArg
from pydoclint.utils.violation import Violation
from pydoclint.utils.yield_arg import YieldArg

SPHINX_MSG_POSTFIX: str = (
    ' (Please read'
    ' https://jsh9.github.io/pydoclint/checking_class_attributes.html'
    ' on how to correctly document class attributes.)'
)


def checkClassAttributesAgainstClassDocstring(
        *,
        node: ast.ClassDef,
        style: str,
        violations: List[Violation],
        lineNum: int,
        msgPrefix: str,
        shouldCheckArgOrder: bool,
        argTypeHintsInSignature: bool,
        argTypeHintsInDocstring: bool,
        skipCheckingShortDocstrings: bool,
) -> None:
    """Check class attribute list against the attribute list in docstring"""
    classAttributes = _collectClassAttributes(node)
    actualArgs: ArgList = _convertClassAttributesIntoArgList(classAttributes)

    classDocstring: str = getDocstring(node)

    if classDocstring == '':
        # We don't check classes without any docstrings.
        # We defer to
        # flake8-docstrings (https://github.com/PyCQA/flake8-docstrings)
        # or pydocstyle (https://www.pydocstyle.org/en/stable/)
        # to determine whether a class needs a docstring.
        return

    try:
        doc: Doc = Doc(docstring=classDocstring, style=style)
    except Exception as excp:
        doc = Doc(docstring='', style=style)
        violations.append(
            Violation(
                code=1,
                line=lineNum,
                msgPrefix=f'Class `{node.name}`:',
                msgPostfix=str(excp).replace('\n', ' '),
            )
        )

    if doc.isShortDocstring and skipCheckingShortDocstrings:
        return

    docArgs: ArgList = doc.attrList

    checkDocArgsLengthAgainstActualArgs(
        docArgs=docArgs,
        actualArgs=actualArgs,
        violations=violations,
        violationForDocArgsLengthShorter=Violation(
            code=601,
            line=lineNum,
            msgPrefix=msgPrefix,
            msgPostfix=SPHINX_MSG_POSTFIX,
        ),
        violationForDocArgsLengthLonger=Violation(
            code=602,
            line=lineNum,
            msgPrefix=msgPrefix,
            msgPostfix=SPHINX_MSG_POSTFIX,
        ),
    )

    checkNameOrderAndTypeHintsOfDocArgsAgainstActualArgs(
        docArgs=docArgs,
        actualArgs=actualArgs,
        violations=violations,
        actualArgsAreClassAttributes=True,
        violationForOrderMismatch=Violation(
            code=604,
            line=lineNum,
            msgPrefix=msgPrefix,
            msgPostfix=SPHINX_MSG_POSTFIX,
        ),
        violationForTypeHintMismatch=Violation(
            code=605,
            line=lineNum,
            msgPrefix=msgPrefix,
            msgPostfix=SPHINX_MSG_POSTFIX,
        ),
        shouldCheckArgOrder=shouldCheckArgOrder,
        argTypeHintsInSignature=argTypeHintsInSignature,
        argTypeHintsInDocstring=argTypeHintsInDocstring,
        lineNum=lineNum,
        msgPrefix=msgPrefix,
    )


def _collectClassAttributes(
        node: ast.ClassDef,
) -> List[Union[ast.Assign, ast.AnnAssign]]:
    if 'body' not in node.__dict__ or len(node.body) == 0:
        return []

    attributes: List[Union[ast.Assign, ast.AnnAssign]] = []
    for item in node.body:
        if isinstance(item, (ast.Assign, ast.AnnAssign)):
            attributes.append(item)

    return attributes


def _convertClassAttributesIntoArgList(
        classAttributes: List[Union[ast.Assign, ast.AnnAssign]],
) -> ArgList:
    atl: List[Arg] = []
    for attr in classAttributes:
        if isinstance(attr, ast.AnnAssign):
            atl.append(Arg.fromAstAnnAssign(attr))
        elif isinstance(attr, ast.Assign):
            if isinstance(attr.targets[0], ast.Tuple):
                atl.extend(ArgList.fromAstAssignWithTupleTarget(attr).infoList)
            else:
                atl.append(Arg.fromAstAssignWithNonTupleTarget(attr))
        else:
            raise InternalError(
                f'Unkonwn type of class attribute: {type(attr)}'
            )

    return ArgList(infoList=atl)


def checkDocArgsLengthAgainstActualArgs(
        *,
        docArgs: ArgList,
        actualArgs: ArgList,
        violations: List[Violation],
        violationForDocArgsLengthShorter: Violation,  # such as V101, V601
        violationForDocArgsLengthLonger: Violation,  # such as V102, V602
) -> None:
    """Check lengths of doc arg list against actual arg list"""
    if docArgs.length < actualArgs.length:
        violations.append(violationForDocArgsLengthShorter)

    if docArgs.length > actualArgs.length:
        violations.append(violationForDocArgsLengthLonger)


def checkNameOrderAndTypeHintsOfDocArgsAgainstActualArgs(
        *,
        docArgs: ArgList,
        actualArgs: ArgList,
        violations: List[Violation],
        actualArgsAreClassAttributes: bool,
        violationForOrderMismatch: Violation,  # such as V104, V604
        violationForTypeHintMismatch: Violation,  # such as V105, V605
        shouldCheckArgOrder: bool,
        argTypeHintsInSignature: bool,
        argTypeHintsInDocstring: bool,
        lineNum: int,
        msgPrefix: str,
) -> None:
    """
    Check the arg/attr list in the docstring against the actual arg/attr
    list (either the function arguments or class attributes).
    """
    if not docArgs.equals(
        actualArgs,
        checkTypeHint=True,
        orderMatters=shouldCheckArgOrder,
    ):
        if docArgs.equals(
            actualArgs,
            checkTypeHint=True,
            orderMatters=False,
        ):
            violations.append(violationForOrderMismatch)
        elif docArgs.equals(
            actualArgs,
            checkTypeHint=False,
            orderMatters=shouldCheckArgOrder,
        ):
            if argTypeHintsInSignature and argTypeHintsInDocstring:
                v105new = appendArgsToCheckToV105(
                    original_v105=violationForTypeHintMismatch,
                    funcArgs=actualArgs,
                    docArgs=docArgs,
                )
                violations.append(v105new)
        elif docArgs.equals(
            actualArgs,
            checkTypeHint=False,
            orderMatters=False,
        ):
            v105new = appendArgsToCheckToV105(
                original_v105=violationForTypeHintMismatch,
                funcArgs=actualArgs,
                docArgs=docArgs,
            )
            violations.append(violationForOrderMismatch)
            violations.append(v105new)
        else:
            argsInFuncNotInDoc: Set[Arg] = actualArgs.subtract(
                docArgs,
                checkTypeHint=False,
            )
            argsInDocNotInFunc: Set[Arg] = docArgs.subtract(
                actualArgs,
                checkTypeHint=False,
            )

            msgPostfixParts: List[str] = []

            string0 = (
                'Attributes in the class definition but not in the'
                if actualArgsAreClassAttributes
                else 'Arguments in the function signature but not in the'
            )

            if argsInFuncNotInDoc:
                msgPostfixParts.append(
                    string0 + f' docstring: {sorted(argsInFuncNotInDoc)}.'
                )

            string1 = (
                ' actual class attributes:'
                if actualArgsAreClassAttributes
                else ' function signature:'
            )

            if argsInDocNotInFunc:
                msgPostfixParts.append(
                    'Arguments in the docstring but not in the'
                    + string1
                    + f' {sorted(argsInDocNotInFunc)}.'
                )

            msgPostfixTemp: str = ' '.join(msgPostfixParts)

            if actualArgsAreClassAttributes:
                msgPostfixTemp += SPHINX_MSG_POSTFIX

            violations.append(
                Violation(
                    code=603 if actualArgsAreClassAttributes else 103,
                    line=lineNum,
                    msgPrefix=msgPrefix,
                    msgPostfix=msgPostfixTemp,
                )
            )


def checkReturnTypesForViolations(
        *,
        style: str,
        returnAnnotation: ReturnAnnotation,
        violationList: List[Violation],
        returnSection: List[ReturnArg],
        violation: Violation,
) -> None:
    """Check return types between function signature and docstring"""
    if style == 'numpy':
        checkReturnTypesForNumpyStyle(
            returnAnnotation=returnAnnotation,
            violationList=violationList,
            returnSection=returnSection,
            violation=violation,
        )
    else:
        checkReturnTypesForGoogleOrSphinxStyle(
            returnAnnotation=returnAnnotation,
            violationList=violationList,
            returnSection=returnSection,
            violation=violation,
        )


def checkReturnTypesForNumpyStyle(
        *,
        returnAnnotation: ReturnAnnotation,
        violationList: List[Violation],
        returnSection: List[ReturnArg],
        violation: Violation,
) -> None:
    """Check return types for numpy docstring style"""
    # If the return annotation is a tuple (such as Tuple[int, str]),
    # we consider both in the docstring to be a valid style:
    #
    # Option 1:
    # >    Returns
    # >    -------
    # >    Tuple[int, str]
    # >        ...
    #
    # Option 2:
    # >    Returns
    # >    -------
    # >    int
    # >        ...
    # >    str
    # >        ...
    #
    #  This is why we are comparing both the decomposed annotation
    #  types and the original annotation type
    returnAnnoItems: List[str] = returnAnnotation.decompose()
    returnAnnoInList: List[str] = returnAnnotation.putAnnotationInList()

    returnSecTypes: List[str] = [stripQuotes(_.argType) for _ in returnSection]

    if returnAnnoInList != returnSecTypes:
        if len(returnAnnoItems) != len(returnSection):
            msg = f'Return annotation has {len(returnAnnoItems)}'
            msg += ' type(s); docstring return section has'
            msg += f' {len(returnSection)} type(s).'
            violationList.append(violation.appendMoreMsg(moreMsg=msg))
        else:
            if not all(
                specialEqual(x, y)
                for x, y in zip(returnSecTypes, returnAnnoItems)
            ):
                msg1 = f'Return annotation types: {returnAnnoItems}; '
                msg2 = f'docstring return section types: {returnSecTypes}'
                violationList.append(violation.appendMoreMsg(msg1 + msg2))


def checkReturnTypesForGoogleOrSphinxStyle(
        *,
        returnAnnotation: ReturnAnnotation,
        violationList: List[Violation],
        returnSection: List[ReturnArg],
        violation: Violation,
) -> None:
    """Check return types for Google or Sphinx docstring style"""
    # The Google docstring style does not allow (or at least does
    # not encourage) splitting tuple return types (such as
    # Tuple[int, str, bool]) into individual types (int, str, and
    # bool).
    # Therefore, in Google-style docstrings, people should always
    # use one compound style for tuples.

    if len(returnSection) > 0:
        retArgType: str = stripQuotes(returnSection[0].argType)
        if returnAnnotation.annotation is None:
            msg = 'Return annotation has 0 type(s); docstring'
            msg += ' return section has 1 type(s).'
            violationList.append(violation.appendMoreMsg(moreMsg=msg))
        elif not specialEqual(retArgType, returnAnnotation.annotation):
            msg = 'Return annotation types: '
            msg += str([returnAnnotation.annotation]) + '; '
            msg += 'docstring return section types: '
            msg += str([retArgType])
            violationList.append(violation.appendMoreMsg(moreMsg=msg))
    else:
        if bool(returnAnnotation.annotation):  # not empty str or not None
            msg = 'Return annotation has 1 type(s); docstring'
            msg += ' return section has 0 type(s).'
            violationList.append(violation.appendMoreMsg(moreMsg=msg))


def checkYieldTypesForViolations(
        *,
        returnAnnotation: ReturnAnnotation,
        violationList: List[Violation],
        yieldSection: List[YieldArg],
        violation: Violation,
        hasGeneratorAsReturnAnnotation: bool,
        hasIteratorOrIterableAsReturnAnnotation: bool,
        requireYieldSectionWhenYieldingNothing: bool,
) -> None:
    """Check yield types between function signature and docstring"""
    # Even though the numpy docstring guide demonstrates that we can
    # write multiple values in the "Yields" section
    # (https://numpydoc.readthedocs.io/en/latest/format.html#yields),
    # in pydoclint we still only require putting all the yielded
    # values into one `Generator[..., ..., ...]`, because it is easier
    # to check and less ambiguous.

    returnAnnoText: Optional[str] = returnAnnotation.annotation
    yieldType: str = extractYieldTypeFromGeneratorOrIteratorAnnotation(
        returnAnnoText,
        hasGeneratorAsReturnAnnotation,
        hasIteratorOrIterableAsReturnAnnotation,
    )

    if len(yieldSection) > 0:
        if returnAnnoText is None:
            msg = 'Return annotation does not exist or is not'
            msg += ' Generator[...]/Iterator[...]/Iterable[...],'
            msg += ' but docstring "yields" section has 1 type(s).'
            violationList.append(violation.appendMoreMsg(moreMsg=msg))
        else:
            if yieldSection[0].argType != yieldType:
                msg = (
                    'The yield type (the 0th arg in Generator[...]'
                    '/Iterator[...]): '
                )
                msg += str(yieldType) + '; '
                msg += 'docstring "yields" section types: '
                msg += str(yieldSection[0].argType)
                violationList.append(violation.appendMoreMsg(moreMsg=msg))
    else:
        if (
            (
                hasGeneratorAsReturnAnnotation
                or hasIteratorOrIterableAsReturnAnnotation
            )
            and yieldType == 'None'
            and not requireYieldSectionWhenYieldingNothing
        ):
            # This means that we don't need to have a "Yields" section in the
            # docstring if the yield type is None.
            pass
        elif returnAnnoText != '':
            msg = 'Return annotation exists, but docstring'
            msg += ' "yields" section does not exist or has 0 type(s).'
            violationList.append(violation.appendMoreMsg(moreMsg=msg))


def extractYieldTypeFromGeneratorOrIteratorAnnotation(
        returnAnnoText: str,
        hasGeneratorAsReturnAnnotation: bool,
        hasIteratorOrIterableAsReturnAnnotation: bool,
) -> str:
    """Extract yield type from Generator or Iterator annotations"""
    try:
        # "Yield type" is the 0th element in a Generator
        # type annotation (Generator[YieldType, SendType,
        # ReturnType])
        # https://docs.python.org/3/library/typing.html#typing.Generator
        # Or it's the 0th (only) element in Iterator
        yieldType: str

        if hasGeneratorAsReturnAnnotation:
            if sys.version_info >= (3, 9):
                yieldType = unparseAnnotation(
                    ast.parse(returnAnnoText).body[0].value.slice.elts[0]
                )
            else:
                yieldType = unparseAnnotation(
                    ast.parse(returnAnnoText).body[0].value.slice.value.elts[0]
                )
        elif hasIteratorOrIterableAsReturnAnnotation:
            yieldType = unparseAnnotation(
                ast.parse(returnAnnoText).body[0].value.slice
            )
        else:
            yieldType = returnAnnoText
    except Exception:
        yieldType = returnAnnoText

    return stripQuotes(yieldType)


def extractReturnTypeFromGenerator(returnAnnoText: str) -> str:
    """Extract return type from Generator annotations"""
    try:
        # "Return type" is the last element in a Generator
        # type annotation (Generator[YieldType, SendType,
        # ReturnType])
        # https://docs.python.org/3/library/typing.html#typing.Generator
        returnType: str
        if sys.version_info >= (3, 9):
            returnType = unparseAnnotation(
                ast.parse(returnAnnoText).body[0].value.slice.elts[-1]
            )
        else:
            returnType = unparseAnnotation(
                ast.parse(returnAnnoText).body[0].value.slice.value.elts[-1]
            )
    except Exception:
        returnType = returnAnnoText

    return stripQuotes(returnType)
